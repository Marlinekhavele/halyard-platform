"""Stores users."""

from collections.abc import Sequence

import sqlalchemy as sa

from accounts import models
from halyard_common import repository


class UserRepository(repository.Repository[models.User]):
    """Stores users."""

    model = models.User

    async def get_by_email(self, email: str) -> models.User | None:
        """Finds a user by email address.

        Args:
            email: The address, already lower-cased.

        Returns:
            The user, or None.
        """
        return await self._scalar(
            sa.select(models.User).where(models.User.email == email)
        )

    async def list_for_company(self, company_id: str) -> Sequence[models.User]:
        """Returns a company's users, ordered by name.

        Args:
            company_id: The company.

        Returns:
            The users.
        """
        return await self._scalars(
            sa.select(models.User)
            .where(models.User.company_id == company_id)
            .order_by(models.User.name)
        )
