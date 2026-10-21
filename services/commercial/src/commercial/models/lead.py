"""ORM model of the commercial service: Lead."""

import sqlalchemy as sa
from sqlalchemy import orm

from commercial.models import base
from halyard_common import db


class Lead(db.IdMixin, db.TimestampMixin, base.Base):
    """A quote request from the public website."""

    __tablename__ = "leads"

    name: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    company: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    email: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    phone: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(50), nullable=True
    )
    origin: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    destination: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    teu_per_year: orm.Mapped[int | None] = orm.mapped_column(
        sa.Integer, nullable=True
    )
    message: orm.Mapped[str | None] = orm.mapped_column(sa.Text, nullable=True)
    # new | contacted | won | lost
    status: orm.Mapped[str] = orm.mapped_column(sa.String(20), default="new")
