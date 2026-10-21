"""Invoice lifecycle and the margin report."""

from collections.abc import Callable, Sequence
import datetime

from sqlalchemy.ext import asyncio as sa_asyncio

from billing import models
from billing import repositories
from billing import schemas
from billing.core import config
from halyard_common import auth
from halyard_common import db
from halyard_common import errors
from halyard_common import events
from halyard_common import outbox

TEU_PER_CONTAINER = {"20DV": 1, "40DV": 2, "40HC": 2, "40RF": 2}


Clock = Callable[[], datetime.date]


class InvoiceService:
    """Invoice lifecycle and the margin report."""

    def __init__(
        self,
        session: sa_asyncio.AsyncSession,
        settings: config.Settings,
        today: Clock = datetime.date.today,
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request or event.
            settings: The service settings.
            today: Returns the current date; replaceable in tests.
        """
        self._session = session
        self._settings = settings
        self._today = today
        self.invoices = repositories.InvoiceRepository(session)
        self.outbox = outbox.OutboxRepository(
            session, models.OutboxEvent, settings.service_name
        )

    def today(self) -> datetime.date:
        """Returns the current date."""
        return self._today()

    # ---- Reactions to other services' events (the consumer commits) ------

    async def draft_for_booking(
        self, booking: events.BookingConfirmed
    ) -> models.Invoice | None:
        """Drafts the invoice of a confirmed booking.

        Args:
            booking: The confirmed booking with its price lines.

        Returns:
            The draft, or None if the booking already has an invoice.
        """
        if await self.invoices.get_by_booking(booking.booking_id):
            return None
        subtotal = sum(line.sell_cents for line in booking.lines)
        vat_rate = self._settings.vat_rate_bp
        vat = round(subtotal * vat_rate / 10_000)
        teu = TEU_PER_CONTAINER.get(booking.container_type, 2)
        invoice = models.Invoice(
            company_id=booking.company_id,
            booking_id=booking.booking_id,
            shipment_ref=booking.booking_ref,
            contact_email=booking.contact_email,
            route=f"{booking.pol}-{booking.pod}",
            container_type=booking.container_type,
            quantity=booking.quantity,
            teu=teu * booking.quantity,
            currency=booking.currency,
            subtotal_cents=subtotal,
            vat_rate_bp=vat_rate,
            vat_cents=vat,
            total_cents=subtotal + vat,
            cost_cents=sum(line.cost_cents for line in booking.lines),
            lines=[
                models.InvoiceLine(
                    position=position,
                    code=line.code,
                    label=line.label,
                    quantity=line.quantity,
                    sell_cents=line.sell_cents,
                    cost_cents=line.cost_cents,
                )
                for position, line in enumerate(booking.lines)
            ],
        )
        return await self.invoices.add(invoice)

    async def issue_on_departure(
        self, milestone: events.MilestoneReached
    ) -> models.Invoice | None:
        """Issues the draft invoice when the vessel departs.

        Args:
            milestone: Any reached milestone; only ``DEPARTED`` has an effect.

        Returns:
            The issued invoice, or None if nothing was issued.
        """
        if milestone.code != "DEPARTED":
            return None
        invoice = await self.invoices.get_by_booking(milestone.booking_id)
        if not invoice or invoice.status != "draft":
            return None
        issue_date = milestone.at.date()
        invoice.status = "issued"
        invoice.number = await self._next_invoice_number(self.today().year)
        invoice.issue_date = issue_date
        invoice.due_date = issue_date + datetime.timedelta(
            days=self._settings.payment_terms_days
        )
        self.outbox.add(
            events.EventType.INVOICE_ISSUED,
            events.InvoiceIssued(
                invoice_id=invoice.id,
                number=invoice.number,
                company_id=invoice.company_id,
                shipment_ref=invoice.shipment_ref,
                total_cents=invoice.total_cents,
                currency=invoice.currency,
                due_date=invoice.due_date,
            ),
        )
        return invoice

    async def record_delivery(
        self, delivered: events.ShipmentDelivered
    ) -> None:
        """Notes the delivery date on the shipment's invoice.

        Args:
            delivered: The delivery event.
        """
        invoice = await self.invoices.get_by_booking(delivered.booking_id)
        if invoice:
            invoice.delivered_at = delivered.delivered_at

    async def void_for_booking(self, booking_id: str) -> None:
        """Voids the draft invoice of a cancelled booking.

        Issued invoices are left alone; they need a credit note.

        Args:
            booking_id: The cancelled booking.
        """
        invoice = await self.invoices.get_by_booking(booking_id)
        if invoice and invoice.status == "draft":
            invoice.status = "void"

    # ---- API use cases ---------------------------------------------------

    async def list_invoices(
        self, user: auth.CurrentUser, status: str | None
    ) -> Sequence[models.Invoice]:
        """Lists invoices the caller may see. Customers never see drafts.

        Args:
            user: The caller.
            status: Only invoices in this status.

        Returns:
            The invoices, newest first.
        """
        if user.is_ops:
            return await self.invoices.list_recent(None, status)
        return await self.invoices.list_recent(
            user.company_id, status, include_drafts=False
        )

    async def get_invoice(
        self, user: auth.CurrentUser, invoice_id: str
    ) -> models.Invoice:
        """Returns an invoice the caller may see.

        Args:
            user: The caller.
            invoice_id: The invoice.

        Returns:
            The invoice.

        Raises:
            errors.NotFoundError: The invoice does not exist, belongs to
                another company, or is a draft and the caller is a customer.
        """
        invoice = await self.invoices.get(invoice_id)
        if (
            not invoice
            or not user.can_see_company(invoice.company_id)
            or (invoice.status == "draft" and not user.is_ops)
        ):
            raise errors.NotFoundError("Invoice not found.")
        return invoice

    async def mark_paid(
        self, user: auth.CurrentUser, invoice_id: str
    ) -> models.Invoice:
        """Records payment of an issued invoice. Ops only.

        Args:
            user: The caller.
            invoice_id: The invoice.

        Returns:
            The paid invoice.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
            errors.NotFoundError: The invoice does not exist.
            errors.ConflictError: The invoice is not issued.
        """
        auth.require_ops(user)
        invoice = await self.invoices.get(invoice_id)
        if not invoice:
            raise errors.NotFoundError("Invoice not found.")
        if invoice.status != "issued":
            raise errors.ConflictError(
                "Only issued invoices can be paid; this one is"
                f" {invoice.status}."
            )
        invoice.status = "paid"
        invoice.paid_at = db.utcnow()
        self.outbox.add(
            events.EventType.INVOICE_PAID,
            events.InvoicePaid(
                invoice_id=invoice.id,
                number=invoice.number,
                company_id=invoice.company_id,
                total_cents=invoice.total_cents,
            ),
        )
        await self._session.commit()
        return invoice

    async def margin_report(
        self, user: auth.CurrentUser
    ) -> schemas.MarginReport:
        """Computes gross profit per shipment, per charge and per TEU. Ops only.

        Args:
            user: The caller.

        Returns:
            The report.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
        """
        auth.require_ops(user)
        invoices = await self.invoices.list_billable()
        today = self.today()
        shipments = [
            schemas.MarginShipment(
                shipment_ref=inv.shipment_ref,
                route=inv.route,
                teu=inv.teu,
                status=inv.status,
                revenue_cents=inv.subtotal_cents,
                cost_cents=inv.cost_cents,
                gross_profit_cents=inv.gross_profit_cents,
                gross_profit_per_teu_cents=_per(
                    inv.gross_profit_cents, inv.teu
                ),
            )
            for inv in invoices
        ]
        by_code: dict[str, schemas.MarginByCharge] = {}
        for inv in invoices:
            for line in inv.lines:
                bucket = by_code.setdefault(
                    line.code,
                    schemas.MarginByCharge(
                        code=line.code,
                        label=line.label.split(" (")[0],
                        revenue_cents=0,
                        gross_profit_cents=0,
                    ),
                )
                bucket.revenue_cents += line.sell_cents
                bucket.gross_profit_cents += line.sell_cents - line.cost_cents
        revenue = sum(s.revenue_cents for s in shipments)
        profit = sum(s.gross_profit_cents for s in shipments)
        teu = sum(s.teu for s in shipments)
        totals = schemas.MarginTotals(
            shipments=len(shipments),
            teu=teu,
            revenue_cents=revenue,
            gross_profit_cents=profit,
            gross_margin_pct=round(profit / revenue * 100, 1) if revenue else 0,
            gross_profit_per_teu_cents=_per(profit, teu),
            open_receivables_cents=sum(
                i.total_cents for i in invoices if i.status == "issued"
            ),
            overdue_cents=sum(
                i.total_cents for i in invoices if i.is_overdue(today)
            ),
        )
        return schemas.MarginReport(
            totals=totals,
            by_charge=sorted(
                by_code.values(), key=lambda b: -b.gross_profit_cents
            ),
            shipments=shipments,
        )

    async def _next_invoice_number(self, year: int) -> str:
        count = await self.invoices.count_numbered_in_year(year)
        return f"INV-{year}-{count + 1:05d}"


def _per(amount: int, teu: int) -> int:
    """Divides an amount by TEU, returning 0 for zero TEU."""
    return round(amount / teu) if teu else 0
