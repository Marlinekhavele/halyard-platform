"""Rate and surcharge maintenance for ops."""

from collections.abc import Sequence
from typing import Any

from commercial import models
from commercial.domain import reference
from commercial.services import base
from halyard_common import auth
from halyard_common import errors


class RateService(base.CommercialService):
    """Rate and surcharge maintenance for ops."""

    async def list_rates(
        self,
        user: auth.CurrentUser,
        origin_region: str | None = None,
        dest_region: str | None = None,
        container_type: str | None = None,
    ) -> Sequence[models.Rate]:
        """Lists rates. Ops only.

        Args:
            user: The caller.
            origin_region: Only this origin region.
            dest_region: Only this destination region.
            container_type: Only this container type.

        Returns:
            The rates.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
        """
        auth.require_ops(user)
        return await self.rates.search(
            origin_region, dest_region, container_type
        )

    async def update_rate(
        self, user: auth.CurrentUser, rate_id: str, changes: dict[str, Any]
    ) -> models.Rate:
        """Changes a rate. Ops only.

        Args:
            user: The caller.
            rate_id: The rate.
            changes: Field names and new values.

        Returns:
            The updated rate.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
            errors.NotFoundError: The rate does not exist.
            errors.InvalidRequestError: Sell would be below buy.
        """
        auth.require_ops(user)
        rate = await self.rates.get(rate_id)
        if not rate:
            raise errors.NotFoundError("Rate not found.")
        for field, value in changes.items():
            setattr(rate, field, value)
        if rate.sell_cents < rate.buy_cents:
            await self._session.rollback()
            raise errors.InvalidRequestError(
                "Sell price is below buy price; this would lose money on"
                " every container."
            )
        await self._session.commit()
        return rate

    async def list_surcharges(
        self, user: auth.CurrentUser
    ) -> Sequence[models.Surcharge]:
        """Lists surcharges. Ops only.

        Args:
            user: The caller.

        Returns:
            The surcharges in display order.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
        """
        auth.require_ops(user)
        return await self.surcharges.list_sorted()

    @staticmethod
    def vessel_suggestions(carrier: str) -> list[str]:
        """Returns known vessel names of a carrier.

        Args:
            carrier: The carrier name.

        Returns:
            Vessel names; empty for unknown carriers.
        """
        return list(reference.VESSELS.get(carrier, []))
