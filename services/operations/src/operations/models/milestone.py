"""ORM model of the operations service: Milestone."""

import datetime
import typing

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from operations.models import base

if typing.TYPE_CHECKING:
    from operations.models.shipment import Shipment


class Milestone(db.IdMixin, base.Base):
    """A planned step of a shipment, recorded when it happens."""

    __tablename__ = "milestones"

    shipment_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("shipments.id"), index=True
    )
    seq: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    code: orm.Mapped[str] = orm.mapped_column(sa.String(30))
    label: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    planned_at: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    actual_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    location: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )

    shipment: orm.Mapped["Shipment"] = orm.relationship(
        back_populates="milestones"
    )
