"""Stores the raw tracking event log."""

from halyard_common import repository
from operations import models


class TrackingEventRepository(repository.Repository[models.TrackingEvent]):
    """Stores the raw tracking event log."""

    model = models.TrackingEvent

    def record(self, event: models.TrackingEvent) -> None:
        """Stages a tracking event without flushing.

        Args:
            event: The event to log.
        """
        self.session.add(event)
