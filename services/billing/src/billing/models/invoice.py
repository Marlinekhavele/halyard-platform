"""ORM models of the billing service: Invoice, InvoiceLine."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from billing.models import base
from halyard_common import db


class Invoice(db.IdMixin, db.TimestampMixin, base.Base):
    """A customer invoice with our partner costs alongside.

    Lifecycle: ``draft`` (booking confirmed) -> ``issued`` (vessel departed)
    -> ``paid``; a draft becomes ``void`` if the booking is cancelled.
    """

    __tablename__ = "invoices"

    # Assigned when issued.
    number: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(20), unique=True, nullable=True
    )
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    booking_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), unique=True)
    shipment_ref: orm.Mapped[str] = orm.mapped_column(sa.String(20), index=True)
    contact_email: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    route: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    container_type: orm.Mapped[str] = orm.mapped_column(sa.String(4))
    quantity: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    teu: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    status: orm.Mapped[str] = orm.mapped_column(
        sa.String(10), default="draft", index=True
    )
    currency: orm.Mapped[str] = orm.mapped_column(sa.String(3), default="EUR")
    subtotal_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    # Basis points.
    vat_rate_bp: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=0)
    vat_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=0)
    total_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    cost_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    issue_date: orm.Mapped[datetime.date | None] = orm.mapped_column(
        sa.Date, nullable=True
    )
    due_date: orm.Mapped[datetime.date | None] = orm.mapped_column(
        sa.Date, nullable=True
    )
    paid_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    delivered_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    lines: orm.Mapped[list["InvoiceLine"]] = orm.relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="InvoiceLine.position",
    )

    @property
    def gross_profit_cents(self) -> int:
        """Revenue before VAT minus partner costs."""
        return self.subtotal_cents - self.cost_cents

    def is_overdue(self, today: datetime.date) -> bool:
        """Whether the invoice is issued and past its due date.

        Args:
            today: The reference date.

        Returns:
            True if overdue.
        """
        return (
            self.status == "issued"
            and self.due_date is not None
            and self.due_date < today
        )


class InvoiceLine(db.IdMixin, base.Base):
    """One charge on an invoice."""

    __tablename__ = "invoice_lines"

    invoice_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("invoices.id"), index=True
    )
    position: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    code: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    label: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    quantity: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    sell_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    cost_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)

    invoice: orm.Mapped[Invoice] = orm.relationship(back_populates="lines")
