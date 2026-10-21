"""Stores companies."""

from collections.abc import Sequence

import sqlalchemy as sa

from accounts import models
from halyard_common import repository

CUSTOMER_NUMBER_OFFSET = 20500


class CompanyRepository(repository.Repository[models.Company]):
    """Stores companies."""

    model = models.Company

    async def list_by_name(self) -> Sequence[models.Company]:
        """Returns every company, alphabetically."""
        return await self._scalars(
            sa.select(models.Company).order_by(models.Company.name)
        )

    async def next_customer_number(self) -> str:
        """Returns the customer number for the next registered company.

        Concurrent sign-ups are serialised until commit, so two companies
        never get the same number.
        """
        await repository.lock_sequence(self.session, "customer-number")
        count = await self.count()
        return f"HLY-{CUSTOMER_NUMBER_OFFSET + count + 1}"
