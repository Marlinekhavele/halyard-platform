"""Repositories of the notifications service, one module per entity."""

from notifications.repositories.notification_repository import (
    NotificationRepository,
)
from notifications.repositories.recipient_repository import RecipientRepository

__all__ = [
    "NotificationRepository",
    "RecipientRepository",
]
