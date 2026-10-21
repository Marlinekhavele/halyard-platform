"""Stores surcharges."""

from collections.abc import Sequence

import sqlalchemy as sa

from commercial import models
from halyard_common import repository


class SurchargeRepository(repository.Repository[models.Surcharge]):
    """Stores surcharges."""

    model = models.Surcharge

    async def list_sorted(self) -> Sequence[models.Surcharge]:
        """Returns every surcharge in display order."""
        return await self._scalars(
            sa.select(models.Surcharge).order_by(models.Surcharge.sort)
        )
