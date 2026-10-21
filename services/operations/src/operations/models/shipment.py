"""ORM models of the operations service: CLOSED_STATUSES, Shipment."""

import datetime
import typing

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from operations.models import base

if typing.TYPE_CHECKING:
    from operations.models.container import Container
    from operations.models.document import Document
    from operations.models.milestone import Milestone


CLOSED_STATUSES = frozenset({"delivered", "cancelled"})


class Shipment(db.IdMixin, db.TimestampMixin, base.Base):
    """A confirmed booking on its way from supplier to consignee."""

    __tablename__ = "shipments"

    ref: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), unique=True, index=True
    )
    booking_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), unique=True)
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    contact_email: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    # booked | in_transit | at_port | customs_hold | delivered | cancelled
    status: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), default="booked", index=True
    )
    pol: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    pod: orm.Mapped[str] = orm.mapped_column(sa.String(5))
    via: orm.Mapped[str | None] = orm.mapped_column(sa.String(5), nullable=True)
    pol_name: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    pod_name: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    via_name: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    carrier: orm.Mapped[str] = orm.mapped_column(sa.String(50))
    vessel: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    voyage: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    etd: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    eta: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    planned_eta: orm.Mapped[datetime.date] = orm.mapped_column(sa.Date)
    container_type: orm.Mapped[str] = orm.mapped_column(sa.String(4))
    commodity: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    incoterm: orm.Mapped[str] = orm.mapped_column(sa.String(3))
    gross_weight_kg: orm.Mapped[int] = orm.mapped_column(sa.Integer)
    bill_of_lading: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(30), nullable=True
    )
    delay_reason: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(300), nullable=True
    )
    hold_reason: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(300), nullable=True
    )
    delivered_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    containers: orm.Mapped[list["Container"]] = orm.relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Container.number",
    )
    milestones: orm.Mapped[list["Milestone"]] = orm.relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Milestone.seq",
    )
    documents: orm.Mapped[list["Document"]] = orm.relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Document.sort",
    )

    @property
    def is_closed(self) -> bool:
        """Whether the shipment is delivered or cancelled."""
        return self.status in CLOSED_STATUSES
