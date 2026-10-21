"""ORM model of the accounts service: Company."""

import typing

import sqlalchemy as sa
from sqlalchemy import orm

from accounts.models import base
from halyard_common import db

if typing.TYPE_CHECKING:
    from accounts.models.user import User


class Company(db.IdMixin, db.TimestampMixin, base.Base):
    """A customer company, or Halyard itself (``kind == "internal"``)."""

    __tablename__ = "companies"

    name: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    customer_number: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), unique=True
    )
    # customer | internal
    kind: orm.Mapped[str] = orm.mapped_column(sa.String(20), default="customer")
    eori: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(20), nullable=True
    )
    vat_id: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(20), nullable=True
    )
    street: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(200), nullable=True
    )
    postal_code: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(10), nullable=True
    )
    city: orm.Mapped[str | None] = orm.mapped_column(
        sa.String(100), nullable=True
    )
    country: orm.Mapped[str] = orm.mapped_column(sa.String(2), default="DE")

    users: orm.Mapped[list["User"]] = orm.relationship(back_populates="company")
