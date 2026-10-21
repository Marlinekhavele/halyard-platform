"""ORM model of the operations service: Container."""

import datetime
import typing

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from operations.models import base

if typing.TYPE_CHECKING:
    from operations.models.shipment import Shipment


class Container(db.IdMixin, base.Base):
    """One container of a shipment."""

    __tablename__ = "containers"

    shipment_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("shipments.id"), index=True
    )
    # ISO 6346
    number: orm.Mapped[str] = orm.mapped_column(
        sa.String(11), unique=True, index=True
    )
    type: orm.Mapped[str] = orm.mapped_column(sa.String(4))
    last_event: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(30), nullable=True
    )
    last_event_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_location: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )

    shipment: orm.Mapped["Shipment"] = orm.relationship(
        back_populates="containers"
    )
