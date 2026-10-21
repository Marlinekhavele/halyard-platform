"""Models of the notifications service, one module per entity."""

from notifications.models.base import Base
from notifications.models.notification import Notification
from notifications.models.outbox import ProcessedEvent
from notifications.models.recipient import Recipient

__all__ = [
    "Base",
    "Notification",
    "ProcessedEvent",
    "Recipient",
]
