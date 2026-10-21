"""ORM model of the commercial service: Port."""

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base


class Port(base.Base):
    """A port we serve, keyed by UN/LOCODE."""

    __tablename__ = "ports"

    code: orm.Mapped[str] = orm.mapped_column(sa.String(5), primary_key=True)
    name: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    country: orm.Mapped[str] = orm.mapped_column(sa.String(2))
    region: orm.Mapped[str] = orm.mapped_column(sa.String(10), index=True)
    is_hub: orm.Mapped[bool] = orm.mapped_column(sa.Boolean, default=False)
