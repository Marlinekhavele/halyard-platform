"""ORM model of the notifications service: Recipient."""

import sqlalchemy as sa
from sqlalchemy import orm

from notifications.models import base


class Recipient(base.Base):
    """Local copy of a user, built from ``accounts.user_created`` events.

    Keeping it here means Notifications never has to call Accounts.
    """

    __tablename__ = "recipients"

    user_id: orm.Mapped[str] = orm.mapped_column(
        sa.String(36), primary_key=True
    )
    company_id: orm.Mapped[str] = orm.mapped_column(sa.String(36), index=True)
    company_name: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    email: orm.Mapped[str] = orm.mapped_column(sa.String(200), index=True)
    name: orm.Mapped[str] = orm.mapped_column(sa.String(200))
    role: orm.Mapped[str] = orm.mapped_column(sa.String(20))
