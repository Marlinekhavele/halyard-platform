"""Stores ports."""

from collections.abc import Sequence

import sqlalchemy as sa

from commercial import models
from halyard_common import repository


class PortRepository(repository.Repository[models.Port]):
    """Stores ports."""

    model = models.Port

    async def list_by_name(self) -> Sequence[models.Port]:
        """Returns every port, alphabetically."""
        return await self._scalars(
            sa.select(models.Port).order_by(models.Port.name)
        )
