"""ORM model of the commercial service: Surcharge."""

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base


class Surcharge(base.Base):
    """A charge around the ocean leg.

    ``basis`` decides how ``sell_value`` and ``cost_value`` are read:
    ``per_container`` and ``per_shipment`` are in cents; ``percent_ocean``
    and ``percent_value`` are in basis points (1400 = 14 %).
    """

    __tablename__ = "surcharges"

    code: orm.Mapped[str] = orm.mapped_column(sa.String(20), primary_key=True)
    label: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    basis: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    sell_value: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    cost_value: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    min_sell_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=0)
    min_cost_cents: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=0)
    # Only applies to this container type, if set.
    container_type: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(4), nullable=True
    )
    # customs | trucking | insurance
    option: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(20), nullable=True
    )
    sort: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=100)
