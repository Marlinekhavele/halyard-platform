"""Shared base for the Operations services."""

from collections.abc import Callable
import datetime

from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import auth
from halyard_common import db
from halyard_common import errors
from halyard_common import outbox
from operations import models
from operations import repositories
from operations.core import config

Clock = Callable[[], datetime.datetime]


def company_scope(user: auth.CurrentUser) -> str | None:
    """Returns the company filter for list queries; None means all."""
    return None if user.is_ops else user.company_id


class OperationsService:
    """Base class holding the repositories every operations use case needs."""

    def __init__(
        self,
        session: sa_asyncio.AsyncSession,
        settings: config.Settings,
        now: Clock = db.utcnow,
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request or event.
            settings: The service settings.
            now: Returns the current UTC time; replaceable in tests.
        """
        self._session = session
        self._settings = settings
        self._now = now
        self.shipments = repositories.ShipmentRepository(session)
        self.containers = repositories.ContainerRepository(session)
        self.documents = repositories.DocumentRepository(session)
        self.tracking_events = repositories.TrackingEventRepository(session)
        self.outbox = outbox.OutboxRepository(
            session, models.OutboxEvent, settings.service_name
        )

    async def get_visible_shipment(
        self, user: auth.CurrentUser, key: str
    ) -> models.Shipment:
        """Returns a shipment the caller may see.

        Args:
            user: The caller.
            key: Shipment id or reference.

        Returns:
            The shipment.

        Raises:
            errors.NotFoundError: The shipment does not exist or is not
                visible.
        """
        shipment = await self.shipments.get_by_id_or_ref(key)
        if not shipment or not user.can_see_company(shipment.company_id):
            raise errors.NotFoundError("Shipment not found.")
        return shipment
