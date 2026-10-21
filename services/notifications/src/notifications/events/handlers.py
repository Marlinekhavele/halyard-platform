"""Event consumers of the Notifications service.

Each handler decides who hears about an event and what the message says.
"""

import datetime

from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import events
from halyard_common import outbox
from notifications import services
from notifications.core import mailer as mailer_lib

CUSTOMER_MILESTONES = frozenset({"DEPARTED", "ARRIVED", "CUSTOMS_RELEASED"})


def euros(cents: int) -> str:
    """Formats cents as euros, for example ``€1,234.50``.

    Args:
        cents: The amount.

    Returns:
        The formatted amount.
    """
    return f"€{cents / 100:,.2f}"


def day(value: datetime.date) -> str:
    """Formats a date like ``Mon 05 Oct 2026``.

    Args:
        value: A date or datetime.

    Returns:
        The formatted date.
    """
    return value.strftime("%a %d %b %Y")


def plural_days(days: int) -> str:
    """Returns ``1 day`` or ``N days``.

    Args:
        days: The number of days.

    Returns:
        The phrase.
    """
    return f"{days} day{'s' if days != 1 else ''}"


class EventHandlers:
    """Turns business events into emails and in-app alerts."""

    def __init__(self, mailer: mailer_lib.Mailer) -> None:
        """Initialises the handlers.

        Args:
            mailer: Sends emails.
        """
        self._mailer = mailer

    def handlers(self) -> dict[str, outbox.EventHandler]:
        """Returns the handler for every consumed event type."""
        event_type = events.EventType
        return {
            event_type.USER_CREATED: self.on_user_created,
            event_type.BOOKING_REQUESTED: self.on_booking_requested,
            event_type.BOOKING_CONFIRMED: self.on_booking_confirmed,
            event_type.MILESTONE_REACHED: self.on_milestone_reached,
            event_type.SHIPMENT_DELAYED: self.on_shipment_delayed,
            event_type.CUSTOMS_HOLD: self.on_customs_hold,
            event_type.DOCUMENT_UPLOADED: self.on_document_uploaded,
            event_type.DOCUMENT_REVIEWED: self.on_document_reviewed,
            event_type.SHIPMENT_DELIVERED: self.on_shipment_delivered,
            event_type.INVOICE_ISSUED: self.on_invoice_issued,
        }

    def _service(
        self, session: sa_asyncio.AsyncSession
    ) -> services.NotificationService:
        return services.NotificationService(session, self._mailer)

    async def on_user_created(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Remembers the user and welcomes new customers."""
        user = events.UserCreated.model_validate(env.data)
        await self._service(session).register_recipient(user)

    async def on_booking_requested(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Asks ops to confirm carrier space."""
        b = events.BookingRequested.model_validate(env.data)
        await self._service(session).notify(
            env.type,
            audience="ops",
            company_id=b.company_id,
            kind="action",
            title=f"New booking request {b.booking_ref}",
            body=(
                f"{b.quantity}× {b.container_type} {b.pol} → {b.pod} with"
                f" {b.carrier}, sailing {day(b.etd)}. Value"
                f" {euros(b.total_sell_cents)}. Confirm space with the"
                " carrier."
            ),
            link="/ops/bookings",
        )

    async def on_booking_confirmed(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Tells the customer their space is confirmed."""
        b = events.BookingConfirmed.model_validate(env.data)
        await self._service(session).notify(
            env.type,
            audience="customer",
            company_id=b.company_id,
            kind="success",
            title=f"Booking {b.booking_ref} confirmed",
            body=(
                f"Space is confirmed on {b.vessel} ({b.voyage}), departing"
                f" {b.pol_name or b.pol} on {day(b.etd)} and arriving in"
                f" {b.pod_name or b.pod} on {day(b.eta)}. Please upload your"
                " commercial invoice and packing list."
            ),
            link=f"/shipments/{b.booking_ref}",
        )

    async def on_milestone_reached(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Tells the customer about departure, arrival and customs release."""
        m = events.MilestoneReached.model_validate(env.data)
        if m.code not in CUSTOMER_MILESTONES:
            return
        await self._service(session).notify(
            env.type,
            audience="customer",
            company_id=m.company_id,
            kind="info",
            title=f"{m.shipment_ref}: {m.label}",
            body=f"{m.label} on {day(m.at)}.",
            link=f"/shipments/{m.shipment_ref}",
        )

    async def on_shipment_delayed(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Warns the customer and ops about a later arrival."""
        d = events.ShipmentDelayed.model_validate(env.data)
        late = plural_days((d.new_eta - d.previous_eta).days)
        body = (
            f"New arrival date {day(d.new_eta)} ({late} later)."
            f" {d.reason or ''}"
        ).strip()
        service = self._service(session)
        for audience in ("customer", "ops"):
            await service.notify(
                env.type,
                audience=audience,
                company_id=d.company_id,
                kind="warning",
                title=f"{d.shipment_ref} is running {late} late",
                body=body,
                link=f"/shipments/{d.shipment_ref}",
            )

    async def on_customs_hold(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Warns the customer and ops about a customs hold."""
        h = events.CustomsHold.model_validate(env.data)
        service = self._service(session)
        for audience in ("customer", "ops"):
            await service.notify(
                env.type,
                audience=audience,
                company_id=h.company_id,
                kind="warning",
                title=f"{h.shipment_ref} is held by customs",
                body=h.reason,
                link=f"/shipments/{h.shipment_ref}",
            )

    async def on_document_uploaded(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Asks the other side to review an uploaded document."""
        d = events.DocumentUploaded.model_validate(env.data)
        service = self._service(session)
        if await service.is_ops_email(d.uploaded_by_email):
            await service.notify(
                env.type,
                audience="customer",
                company_id=d.company_id,
                kind="action",
                title=f"{d.shipment_ref}: {d.label} ready for your approval",
                body=(
                    f"Please check the {d.label.lower()} and approve it, or"
                    " tell us what to change."
                ),
                link="/documents",
            )
        else:
            await service.notify(
                env.type,
                audience="ops",
                company_id=d.company_id,
                kind="action",
                title=f"{d.shipment_ref}: {d.label} uploaded",
                body=(
                    f"Uploaded by {d.uploaded_by_email}. Check and approve it."
                ),
                link="/ops/documents",
            )

    async def on_document_reviewed(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Tells the uploader whether their document was approved."""
        d = events.DocumentReviewed.model_validate(env.data)
        service = self._service(session)
        if await service.is_ops_email(d.reviewed_by_email):
            if d.approved:
                title = f"{d.shipment_ref}: {d.label} approved"
                await service.notify(
                    env.type,
                    audience="customer",
                    company_id=d.company_id,
                    kind="success",
                    title=title,
                    body="No further action needed.",
                    link=f"/shipments/{d.shipment_ref}",
                )
            else:
                await service.notify(
                    env.type,
                    audience="customer",
                    company_id=d.company_id,
                    kind="action",
                    title=f"{d.shipment_ref}: {d.label} needs changes",
                    body=d.note or "Please upload a corrected version.",
                    link="/documents",
                )
            return
        if d.approved:
            verdict, kind = "approved", "info"
            title = f"{d.shipment_ref}: customer approved on {d.label}"
        else:
            verdict, kind = f"sent back: {d.note}", "action"
            title = f"{d.shipment_ref}: customer requested changes on {d.label}"
        await service.notify(
            env.type,
            audience="ops",
            company_id=d.company_id,
            kind=kind,
            title=title,
            body=verdict,
            link="/ops/documents",
        )

    async def on_shipment_delivered(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Tells the customer their containers arrived."""
        d = events.ShipmentDelivered.model_validate(env.data)
        await self._service(session).notify(
            env.type,
            audience="customer",
            company_id=d.company_id,
            kind="success",
            title=f"{d.shipment_ref} delivered",
            body=(
                f"Your containers were delivered on {day(d.delivered_at)}."
                " Thank you for shipping with Halyard."
            ),
            link=f"/shipments/{d.shipment_ref}",
        )

    async def on_invoice_issued(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Sends the customer their invoice summary."""
        i = events.InvoiceIssued.model_validate(env.data)
        await self._service(session).notify(
            env.type,
            audience="customer",
            company_id=i.company_id,
            kind="info",
            title=f"Invoice {i.number} for {i.shipment_ref}",
            body=f"{euros(i.total_cents)}, due {day(i.due_date)}.",
            link="/invoices",
        )
