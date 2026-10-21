"""Stores bookings."""

from collections.abc import Sequence
import datetime

import sqlalchemy as sa

from commercial import models
from commercial.repositories import references
from halyard_common import repository


class BookingRepository(repository.Repository[models.Booking]):
    """Stores bookings."""

    model = models.Booking

    async def next_ref(self, today: datetime.date) -> str:
        """Returns the reference for the next booking, like ``HLY-26-00001``.

        Args:
            today: Supplies the year.

        Returns:
            The reference.
        """
        return await references.next_ref(self, "HLY", today)

    async def list_recent(
        self, company_id: str | None, status: str | None = None
    ) -> Sequence[models.Booking]:
        """Returns bookings, newest first.

        Args:
            company_id: Only this company's bookings; None for all.
            status: Only bookings in this status.

        Returns:
            The bookings.
        """
        stmt = sa.select(models.Booking)
        if company_id is not None:
            stmt = stmt.where(models.Booking.company_id == company_id)
        if status:
            stmt = stmt.where(models.Booking.status == status)
        return await self._scalars(
            stmt.order_by(models.Booking.created_at.desc())
        )
