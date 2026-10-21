"""ORM model of the operations service: Document."""

import datetime
import typing

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from operations.models import base

if typing.TYPE_CHECKING:
    from operations.models.shipment import Shipment


class Document(db.IdMixin, db.TimestampMixin, base.Base):
    """A shipment document and its review state.

    Customer documents: ``required`` -> ``uploaded`` (ops checks) ->
    ``approved``, or back to ``required`` with a note.

    Ops documents: ``not_due`` -> ``review`` (customer approves) ->
    ``approved``, or back to ``not_due``.
    """

    __tablename__ = "documents"

    shipment_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("shipments.id"), index=True
    )
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    doc_type: orm.Mapped[str] = orm.mapped_column(sa.String(40))
    label: orm.Mapped[str] = orm.mapped_column(sa.String(100))
    sort: orm.Mapped[int] = orm.mapped_column(sa.Integer, default=100)
    status: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), default="required", index=True
    )
    due_date: orm.Mapped[datetime.date | None] = orm.mapped_column(
        sa.Date, nullable=True
    )
    note: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(500), nullable=True
    )
    filename: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(255), nullable=True
    )
    storage_key: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(255), nullable=True
    )
    content_type: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    size_bytes: orm.Mapped[int | None] = orm.mapped_column(
        sa.Integer, nullable=True
    )
    checks: orm.Mapped[list[dict] | None] = orm.mapped_column(
        sa.JSON, nullable=True
    )
    uploaded_by: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    uploaded_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    reviewed_by: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    reviewed_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    shipment: orm.Mapped["Shipment"] = orm.relationship(
        back_populates="documents"
    )
