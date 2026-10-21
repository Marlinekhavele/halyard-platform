"""Stores quotes and their options."""

from collections.abc import Sequence
import datetime

import sqlalchemy as sa

from commercial import models
from commercial.repositories import references
from halyard_common import repository


class QuoteRepository(repository.Repository[models.Quote]):
    """Stores quotes and their options."""

    model = models.Quote

    async def next_ref(self, today: datetime.date) -> str:
        """Returns the reference for the next quote, like ``Q-26-00001``.

        Args:
            today: Supplies the year.

        Returns:
            The reference.
        """
        return await references.next_ref(self, "Q", today)

    async def claim_for_booking(self, quote_id: str) -> bool:
        """Atomically marks an open quote as accepted.

        The database applies the status check and the change together, so of
        two simultaneous bookings on the same quote exactly one succeeds.

        Args:
            quote_id: The quote.

        Returns:
            True if this caller claimed the quote; False if it was not open.
        """
        result = await self.session.execute(
            sa.update(models.Quote)
            .where(models.Quote.id == quote_id, models.Quote.status == "open")
            .values(status="accepted")
        )
        return result.rowcount == 1

    async def list_recent(
        self, company_id: str | None, limit: int
    ) -> Sequence[models.Quote]:
        """Returns the newest quotes.

        Args:
            company_id: Only this company's quotes; None for all.
            limit: Maximum number of quotes.

        Returns:
            The quotes, newest first.
        """
        stmt = sa.select(models.Quote)
        if company_id is not None:
            stmt = stmt.where(models.Quote.company_id == company_id)
        stmt = stmt.order_by(models.Quote.created_at.desc()).limit(limit)
        return await self._scalars(stmt)
