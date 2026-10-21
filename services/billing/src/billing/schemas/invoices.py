"""API request and response models: invoices."""

import datetime
from typing import Self

import pydantic

from billing import models


class InvoiceLineOut(pydantic.BaseModel):
    """One charge. ``cost_cents`` is only shown to ops."""

    code: str
    label: str
    quantity: int
    sell_cents: int
    cost_cents: int | None = None


class InvoiceOut(pydantic.BaseModel):
    """An invoice."""

    id: str
    number: str | None
    company_id: str
    booking_id: str
    shipment_ref: str
    route: str
    container_type: str
    quantity: int
    teu: int
    status: str
    currency: str
    subtotal_cents: int
    vat_rate_bp: int
    vat_cents: int
    total_cents: int
    cost_cents: int | None = None
    gross_profit_cents: int | None = None
    issue_date: datetime.date | None
    due_date: datetime.date | None
    overdue: bool
    lines: list[InvoiceLineOut]

    @classmethod
    def from_model(
        cls, invoice: models.Invoice, show_cost: bool, today: datetime.date
    ) -> Self:
        """Builds the response for a stored invoice.

        Args:
            invoice: The stored invoice.
            show_cost: Whether to include costs and gross profit.
            today: Reference date for ``overdue``.

        Returns:
            The response model.
        """
        return cls(
            id=invoice.id,
            number=invoice.number,
            company_id=invoice.company_id,
            booking_id=invoice.booking_id,
            shipment_ref=invoice.shipment_ref,
            route=invoice.route,
            container_type=invoice.container_type,
            quantity=invoice.quantity,
            teu=invoice.teu,
            status=invoice.status,
            currency=invoice.currency,
            subtotal_cents=invoice.subtotal_cents,
            vat_rate_bp=invoice.vat_rate_bp,
            vat_cents=invoice.vat_cents,
            total_cents=invoice.total_cents,
            cost_cents=invoice.cost_cents if show_cost else None,
            gross_profit_cents=(
                invoice.gross_profit_cents if show_cost else None
            ),
            issue_date=invoice.issue_date,
            due_date=invoice.due_date,
            overdue=invoice.is_overdue(today),
            lines=[
                InvoiceLineOut(
                    code=line.code,
                    label=line.label,
                    quantity=line.quantity,
                    sell_cents=line.sell_cents,
                    cost_cents=line.cost_cents if show_cost else None,
                )
                for line in invoice.lines
            ],
        )
