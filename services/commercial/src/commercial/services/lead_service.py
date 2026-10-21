"""Website leads."""

from collections.abc import Sequence

from commercial import models
from commercial import schemas
from commercial.services import base
from halyard_common import auth
from halyard_common import errors


class LeadService(base.CommercialService):
    """Website leads."""

    async def create_lead(self, lead: schemas.LeadCreate) -> None:
        """Stores a website lead, silently dropping honeypot hits.

        Args:
            lead: The submission.
        """
        if lead.website:  # Honeypot filled in: accept, but don't store.
            return
        await self.leads.add(
            models.Lead(**lead.model_dump(exclude={"website"}))
        )
        await self._session.commit()

    async def list_leads(self, user: auth.CurrentUser) -> Sequence[models.Lead]:
        """Lists leads, newest first. Ops only.

        Args:
            user: The caller.

        Returns:
            The leads.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
        """
        auth.require_ops(user)
        return await self.leads.list_recent()

    async def update_status(
        self, user: auth.CurrentUser, lead_id: str, status: str
    ) -> models.Lead:
        """Moves a lead through the sales pipeline. Ops only.

        Args:
            user: The caller.
            lead_id: The lead.
            status: ``new``, ``contacted``, ``won`` or ``lost``.

        Returns:
            The updated lead.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
            errors.NotFoundError: The lead does not exist.
        """
        auth.require_ops(user)
        lead = await self.leads.get(lead_id)
        if not lead:
            raise errors.NotFoundError("Lead not found.")
        lead.status = status
        await self._session.commit()
        return lead
