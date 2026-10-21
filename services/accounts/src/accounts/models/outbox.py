"""Outbox and inbox tables for reliable event publishing and consumption."""

from accounts.models import base
from halyard_common import outbox


class OutboxEvent(outbox.OutboxMixin, base.Base):
    """Events waiting to be published."""

    __tablename__ = "outbox"


class ProcessedEvent(outbox.ProcessedEventMixin, base.Base):
    """Ids of events already consumed."""

    __tablename__ = "processed_events"
