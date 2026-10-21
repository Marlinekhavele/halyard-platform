"""Event consumers of the Billing service."""

from sqlalchemy.ext import asyncio as sa_asyncio

from billing import services
from billing.core import config
from halyard_common import events
from halyard_common import outbox


class EventHandlers:
    """Keeps invoices in step with bookings and shipments."""

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
            events.EventType.MILESTONE_REACHED: self.on_milestone_reached,
            events.EventType.SHIPMENT_DELIVERED: self.on_shipment_delivered,
        }

    def _service(
        self, session: sa_asyncio.AsyncSession
    ) -> services.InvoiceService:
        return services.InvoiceService(session, self._settings)

    async def on_booking_confirmed(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Drafts the invoice of a confirmed booking.

        Args:
            session: The consumer's transaction.
            env: The ``commercial.booking_confirmed`` event.
        """
        await self._service(session).draft_for_booking(
            events.BookingConfirmed.model_validate(env.data)
        )

    async def on_booking_cancelled(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Voids the draft invoice of a cancelled booking.

        Args:
            session: The consumer's transaction.
            env: The ``commercial.booking_cancelled`` event.
        """
        cancelled = events.BookingCancelled.model_validate(env.data)
        await self._service(session).void_for_booking(cancelled.booking_id)

    async def on_milestone_reached(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Issues the invoice when the vessel departs.

        Args:
            session: The consumer's transaction.
            env: The ``operations.milestone_reached`` event.
        """
        await self._service(session).issue_on_departure(
            events.MilestoneReached.model_validate(env.data)
        )

    async def on_shipment_delivered(
        self, session: sa_asyncio.AsyncSession, env: events.EventEnvelope
    ) -> None:
        """Records the delivery date on the invoice.

        Args:
            session: The consumer's transaction.
            env: The ``operations.shipment_delivered`` event.
        """
        await self._service(session).record_delivery(
            events.ShipmentDelivered.model_validate(env.data)
        )
