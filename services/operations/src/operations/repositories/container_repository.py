"""Stores containers."""

import sqlalchemy as sa

from halyard_common import repository
from operations import models


class ContainerRepository(repository.Repository[models.Container]):
    """Stores containers."""

    model = models.Container

    async def get_by_number(self, number: str) -> models.Container | None:
        """Finds a container by its ISO 6346 number.

        Args:
            number: Normalised number without spaces, upper case.

        Returns:
            The container, or None.
        """
        return await self._scalar(
            sa.select(models.Container).where(models.Container.number == number)
        )
