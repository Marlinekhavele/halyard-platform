"""Stores website leads."""

from collections.abc import Sequence

import sqlalchemy as sa

from commercial import models
from halyard_common import repository


class LeadRepository(repository.Repository[models.Lead]):
    """Stores website leads."""

    model = models.Lead

    async def list_recent(self) -> Sequence[models.Lead]:
        """Returns every lead, newest first."""
        return await self._scalars(
            sa.select(models.Lead).order_by(models.Lead.created_at.desc())
        )
