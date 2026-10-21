"""ORM model of the notifications service: Notification."""

import datetime

import sqlalchemy as sa
from sqlalchemy import orm

from halyard_common import db
from notifications.models import base


class Notification(db.IdMixin, base.Base):
    """An in-app alert, possibly also sent by email."""

    __tablename__ = "notifications"

    # customer | ops
    audience: orm.Mapped[str] = orm.mapped_column(sa.String(10), index=True)
    company_id: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(36), index=True, nullable=True
    )
    # info | success | warning | action
    kind: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    title: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    body: orm.Mapped[str] = orm.mapped_column(sa.Text)
    link: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    event_type: orm.Mapped[str] = orm.mapped_column(sa.String(80))
    emailed_to: orm.Mapped[str | None] = orm.mapped_column(
        sa.Text, nullable=True
    )
    email_status: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), default="skipped"
    )
    created_at: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), default=db.utcnow, index=True
    )
    read_at: orm.Mapped[datetime.datetime | None] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
