"""ORM model of the accounts service: User."""

import typing

import sqlalchemy as sa
from sqlalchemy import orm

from accounts.models import base
from halyard_common import db

if typing.TYPE_CHECKING:
    from accounts.models.company import Company


class User(db.IdMixin, db.TimestampMixin, base.Base):
    """A person who signs in."""

    __tablename__ = "users"

    company_id: orm.Mapped[str] = orm.mapped_column(
        sa.ForeignKey("companies.id"), index=True
    )
    email: orm.Mapped[str] = orm.mapped_column(
        sa.String(200), unique=True, index=True
    )
    name: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    password_hash: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    # customer_admin | customer | ops | admin
    role: orm.Mapped[str] = orm.mapped_column(sa.String(20))
    is_active: orm.Mapped[bool] = orm.mapped_column(default=True)

    company: orm.Mapped["Company"] = orm.relationship(back_populates="users")
