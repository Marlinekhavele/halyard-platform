"""Outbox and inbox tables for reliable event publishing and consumption."""

from halyard_common import outbox
from notifications.models import base


class ProcessedEvent(outbox.ProcessedEventMixin, base.Base):
    """Ids of events already consumed."""

    __tablename__ = "processed_events"
