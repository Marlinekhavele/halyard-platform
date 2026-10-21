"""ORM model of the commercial service: Rate."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base
from halyard_common import db


class Rate(db.IdMixin, db.TimestampMixin, base.Base):
    """What a carrier charges us (buy) and we charge (sell) on a trade lane."""

    __tablename__ = "rates"

    origin_region: orm.Mapped[str] = orm.mapped_column(
        sa.String(10), index=True
    )
    dest_region: orm.Mapped[str] = orm.mapped_column(sa.String(10), index=True)
    carrier: orm.Mapped[str] = orm.mapped_column(sa.String(50))
    # direct | transshipment
    service: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    via_port: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(5), nullable=True
    )
    container_type: orm.Mapped[str] = orm.mapped_column(
        sa.String(4), index=True
    )
    buy_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    sell_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    transit_days: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    # 0 = Monday
    sailing_weekday: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    co2_factor: orm.Mapped[float] = orm.mapped_column(sa.Float, default=1.0)
    valid_until: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    active: orm.Mapped[bool] = orm.mapped_column(sa.Boolean, default=True)
