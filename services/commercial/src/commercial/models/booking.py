"""ORM model of the commercial service: Booking."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base
from halyard_common import db


class Booking(db.IdMixin, db.TimestampMixin, base.Base):
    """A customer's request to ship one quote option."""

    __tablename__ = "bookings"

    ref: orm.Mapped[str] = orm.mapped_column(sa.String(20), unique=True)
    quote_id: orm.Mapped[str] = orm.mapped_column(sa.ForeignKey("quotes.id"))
    option_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("quote_options.id")
    )
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    requested_by: orm.Mapped[str] = orm.mapped_column(sa.String(36))
    requested_by_email: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    # requested | confirmed | cancelled
    status: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), default="requested"
    )
    pol: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    pod: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    via_port: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(5), nullable=True
    )
    carrier: orm.Mapped[str] = orm.mapped_column(sa.String(50))
    container_type: orm.Mapped[str] = orm.mapped_column(sa.String(4))
    quantity: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    commodity: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    incoterm: orm.Mapped[str] = orm.mapped_column(sa.String(3))
    gross_weight_kg: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    cargo_value_cents: orm.Mapped[int] = orm.mapped_column(
        sa.Integer, default=0
    )
    supplier_name: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    notes: orm.Mapped[str | None] = orm.mapped_column(sa.Text, nullable=True)
    etd: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    eta: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    vessel: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    voyage: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(20), nullable=True
    )
    total_sell_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    total_cost_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    lines: orm.Mapped[list[dict]] = orm.mapped_column(sa.JSON)
    confirmed_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    confirmed_by: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    cancel_reason: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(300), nullable=True
    )
