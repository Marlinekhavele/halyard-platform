"""Shared base for the Commercial services."""

from collections.abc import Callable
import datetime

from sqlalchemy.ext import asyncio as sa_asyncio

from commercial import models
from commercial import repositories
from commercial.core import config
from halyard_common import auth
from halyard_common import errors
from halyard_common import outbox

Clock = Callable[[], datetime.date]


def company_scope(user: auth.CurrentUser) -> str | None:
    """Returns the company filter for list queries; None means all."""
    return None if user.is_ops else user.company_id


class CommercialService:
    """Base class holding the repositories every commercial use case needs."""

    def __init__(
        self,
        session: sa_asyncio.AsyncSession,
        settings: config.Settings,
        today: Clock = datetime.date.today,
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request or event.
            settings: The service settings.
            today: Returns the current date; replaceable in tests.
        """
        self._session = session
        self._settings = settings
        self._today = today
        self.ports = repositories.PortRepository(session)
        self.rates = repositories.RateRepository(session)
        self.surcharges = repositories.SurchargeRepository(session)
        self.quotes = repositories.QuoteRepository(session)
        self.bookings = repositories.BookingRepository(session)
        self.leads = repositories.LeadRepository(session)
        self.outbox = outbox.OutboxRepository(
            session, models.OutboxEvent, settings.service_name
        )

    def today(self) -> datetime.date:
        """Returns the current date."""
        return self._today()

    async def get_port(self, code: str) -> models.Port:
        """Returns a served port.

        Args:
            code: UN/LOCODE, any case.

        Returns:
            The port.

        Raises:
            errors.InvalidRequestError: We do not serve the port.
        """
        port = await self.ports.get(code.upper())
        if not port:
            raise errors.InvalidRequestError(f"We don't serve port {code} yet.")
        return port
