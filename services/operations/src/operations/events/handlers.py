"""Event consumers of the Operations service."""

from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import events
from halyard_common import outbox
from operations import services
from operations.core import config


class EventHandlers:
    """Reacts to Commercial booking events."""

    def __init__(self, settings: config.Settings) -> None:
        """Initialises the handlers.

        Args:
            settings: The service settings.
        """
        self._settings = settings

    def handlers(self) -> dict[str, outbox.EventHandler]:
        """Returns the handler for every consumed event type."""
        return {
            events.EventType.BOOKING_CONFIRMED: self.on_booking_confirmed,
            events.EventType.BOOKING_CANCELLED: self.on_booking_cancelled,
        }

    async def on_booking_confirmed(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Opens the shipment of a confirmed booking.

        Args:
            session: The consumer's transaction.
            env: The ``commercial.booking_confirmed`` event.
        """
        booking = events.BookingConfirmed.model_validate(env.data)
        await services.ShipmentService(
            session, self._settings
        ).open_for_booking(booking)

    async def on_booking_cancelled(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Cancels the shipment of a cancelled booking.

        Args:
            session: The consumer's transaction.
            env: The ``commercial.booking_cancelled`` event.
        """
        cancelled = events.BookingCancelled.model_validate(env.data)
        await services.ShipmentService(
            session, self._settings
        ).cancel_for_booking(cancelled.booking_id)
