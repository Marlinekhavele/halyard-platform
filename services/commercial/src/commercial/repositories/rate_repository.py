"""Stores rates."""

from collections.abc import Sequence
import datetime

import sqlalchemy as sa

from commercial import models
from halyard_common import repository


class RateRepository(repository.Repository[models.Rate]):
    """Stores rates."""

    model = models.Rate

    async def find_bookable(
        self,
        origin_region: str,
        dest_region: str,
        container_type: str,
        on: datetime.date,
    ) -> Sequence[models.Rate]:
        """Returns active, valid rates for a lane and container type.

        Args:
            origin_region: Region of the port of loading.
            dest_region: Region of the port of discharge.
            container_type: ISO size-type code, for example ``40HC``.
            on: Rates must be valid on this date.

        Returns:
            The matching rates.
        """
        return await self._scalars(
            sa.select(models.Rate).where(
                models.Rate.origin_region == origin_region,
                models.Rate.dest_region == dest_region,
                models.Rate.container_type == container_type,
                models.Rate.active.is_(True),
                models.Rate.valid_until >= on,
            )
        )

    async def search(
        self,
        origin_region: str | None = None,
        dest_region: str | None = None,
        container_type: str | None = None,
    ) -> Sequence[models.Rate]:
        """Lists rates, optionally filtered, cheapest first per lane.

        Args:
            origin_region: Only this origin region.
            dest_region: Only this destination region.
            container_type: Only this container type.

        Returns:
            The rates.
        """
        rate = models.Rate
        stmt = sa.select(rate).order_by(
            rate.origin_region,
            rate.dest_region,
            rate.container_type,
            rate.sell_cents,
        )
        if origin_region:
            stmt = stmt.where(rate.origin_region == origin_region)
        if dest_region:
            stmt = stmt.where(rate.dest_region == dest_region)
        if container_type:
            stmt = stmt.where(rate.container_type == container_type)
        return await self._scalars(stmt)
