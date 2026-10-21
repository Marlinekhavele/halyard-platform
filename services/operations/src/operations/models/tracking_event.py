"""ORM model of the operations service: TrackingEvent."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from operations.models import base


class TrackingEvent(base.Base):
    """Raw log of every event from the tracking provider or the simulator."""

    __tablename__ = "tracking_events"

    id: orm.Mapped[str] = orm.mapped_column(
        sa.String(36), primary_key=True, default=db.new_id
    )
    shipment_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    container_number: orm.Mapped[str] = orm.mapped_column(sa.String(11))
    event: orm.Mapped[str] = orm.mapped_column(sa.String(30))
    occurred_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True)
    )
    location: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    description: orm.Mapped[str | None] = orm.mapped_column(
        sa.Text, nullable=True
    )
    raw: orm.Mapped[dict] = orm.mapped_column(sa.JSON)
    received_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=db.utcnow
    )
