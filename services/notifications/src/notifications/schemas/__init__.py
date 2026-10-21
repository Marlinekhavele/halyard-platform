"""Schemas of the notifications service, one module per feature."""

from notifications.schemas.notifications import NotificationOut
from notifications.schemas.notifications import StatusOut

__all__ = [
    "NotificationOut",
    "StatusOut",
]
