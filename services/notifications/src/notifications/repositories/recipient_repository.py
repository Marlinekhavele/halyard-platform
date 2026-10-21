"""Stores the local copy of users."""

import sqlalchemy as sa

from halyard_common import auth
from halyard_common import repository
from notifications import models


class RecipientRepository(repository.Repository[models.Recipient]):
    """Stores the local copy of users."""

    model = models.Recipient

    async def ops_emails(self) -> list[str]:
        """Returns the email addresses of every ops user."""
        return list(
            await self._scalars(
                sa.select(models.Recipient.email).where(
                    models.Recipient.role.in_(auth.OPS_ROLES)
                )
            )
        )

    async def customer_emails(self, company_id: str | None) -> list[str]:
        """Returns the email addresses of a customer company's users.

        Args:
            company_id: The company.

        Returns:
            The addresses; ops users of that company are excluded.
        """
        recipient = models.Recipient
        return list(
            await self._scalars(
                sa.select(recipient.email).where(
                    recipient.company_id == company_id,
                    recipient.role.not_in(auth.OPS_ROLES),
                )
            )
        )

    async def role_of(self, email: str) -> str | None:
        """Returns the role of the user with an email address.

        Args:
            email: The address.

        Returns:
            The role, or None for unknown addresses.
        """
        return await self.session.scalar(
            sa.select(models.Recipient.role).where(
                models.Recipient.email == email
            )
        )
