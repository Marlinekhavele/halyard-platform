"""ORM models of the commercial service: Quote, QuoteOption."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base
from halyard_common import db


class Quote(db.IdMixin, db.TimestampMixin, base.Base):
    """A saved, bookable price request with up to three options."""

    __tablename__ = "quotes"

    ref: orm.Mapped[str] = orm.mapped_column(sa.String(20), unique=True)
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    created_by: orm.Mapped[str] = orm.mapped_column(sa.String(36))
    created_by_email: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    pol: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    pod: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    container_type: orm.Mapped[str] = orm.mapped_column(sa.String(4))
    quantity: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    ready_date: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    incoterm: orm.Mapped[str] = orm.mapped_column(sa.String(3))
    commodity: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    cargo_value_cents: orm.Mapped[int] = orm.mapped_column(
        sa.Integer, default=0
    )
    customs: orm.Mapped[bool] = orm.mapped_column(sa.Boolean, default=False)
    trucking: orm.Mapped[bool] = orm.mapped_column(sa.Boolean, default=False)
    insurance: orm.Mapped[bool] = orm.mapped_column(sa.Boolean, default=False)
    # open | accepted | expired
    status: orm.Mapped[str] = orm.mapped_column(sa.String(20), default="open")
    valid_until: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)

    options: orm.Mapped[list["QuoteOption"]] = orm.relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteOption.position",
        lazy="selectin",
    )

    def status_on(self, today: datetime.date) -> str:
        """Returns the status, reporting open quotes past validity as expired.

        Args:
            today: The reference date.

        Returns:
            ``open``, ``accepted`` or ``expired``.
        """
        if self.status == "open" and self.valid_until < today:
            return "expired"
        return self.status


class QuoteOption(db.IdMixin, base.Base):
    """One priced sailing on a quote."""

    __tablename__ = "quote_options"

    quote_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("quotes.id"), index=True
    )
    position: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    label: orm.Mapped[str] = orm.mapped_column(sa.String(30))
    rate_id: orm.Mapped[str] = orm.mapped_column(sa.String(36))
    carrier: orm.Mapped[str] = orm.mapped_column(sa.String(50))
    service: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    via_port: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(5), nullable=True
    )
    etd: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    eta: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    transit_days: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    co2_kg: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    total_sell_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    total_cost_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    lines: orm.Mapped[list[dict]] = orm.mapped_column(sa.JSON)

    quote: orm.Mapped[Quote] = orm.relationship(back_populates="options")
