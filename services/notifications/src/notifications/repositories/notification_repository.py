"""Stores notifications."""

from collections.abc import Sequence
import datetime
from typing import Any

import sqlalchemy as sa

from halyard_common import auth
from halyard_common import repository
from notifications import models


def _visible_to(user: auth.CurrentUser) -> Any:
    """Returns the filter selecting notifications meant for a user."""
    notification = models.Notification
    if user.is_ops:
        return notification.audience == "ops"
    return sa.and_(
        notification.audience == "customer",
        notification.company_id == user.company_id,
    )


class NotificationRepository(repository.Repository[models.Notification]):
    """Stores notifications."""

    model = models.Notification

    async def list_for(
        self, user: auth.CurrentUser, limit: int
    ) -> Sequence[models.Notification]:
        """Returns a user's newest notifications.

        Ops users see the ops feed; customers see their company's feed.

        Args:
            user: The reader.
            limit: Maximum number of notifications.

        Returns:
            The notifications, newest first.
        """
        return await self._scalars(
            sa.select(models.Notification)
            .where(_visible_to(user))
            .order_by(models.Notification.created_at.desc())
            .limit(limit)
        )

    async def mark_all_read(
        self, user: auth.CurrentUser, at: datetime.datetime
    ) -> None:
        """Marks every unread notification of a user's feed as read.

        Args:
            user: The reader.
            at: The read timestamp.
        """
        await self.session.execute(
            sa.update(models.Notification)
            .where(_visible_to(user), models.Notification.read_at.is_(None))
            .values(read_at=at)
        )
