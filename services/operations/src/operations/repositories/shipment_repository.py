"""Stores shipments with their containers, milestones and documents."""

from collections.abc import Collection, Sequence

import sqlalchemy as sa

from halyard_common import repository
from operations import models


class ShipmentRepository(repository.Repository[models.Shipment]):
    """Stores shipments with their containers, milestones and documents."""

    model = models.Shipment

    async def get_by_id_or_ref(self, key: str) -> models.Shipment | None:
        """Finds a shipment by id or by reference.

        Args:
            key: A shipment id or reference such as ``HLY-26-00001``.

        Returns:
            The shipment, or None.
        """
        shipment = models.Shipment
        return await self._scalar(
            sa.select(shipment).where(
                sa.or_(shipment.id == key, shipment.ref == key)
            )
        )

    async def get_by_booking(self, booking_id: str) -> models.Shipment | None:
        """Finds the shipment of a booking.

        Args:
            booking_id: The Commercial booking id.

        Returns:
            The shipment, or None.
        """
        return await self._scalar(
            sa.select(models.Shipment).where(
                models.Shipment.booking_id == booking_id
            )
        )

    async def list_by_eta(
        self,
        company_id: str | None,
        status: str | None = None,
        exclude_statuses: Collection[str] = (),
    ) -> Sequence[models.Shipment]:
        """Lists shipments, earliest arrival first.

        Args:
            company_id: Only this company's shipments; None for all.
            status: Only shipments in this status.
            exclude_statuses: Leave out shipments in these statuses.

        Returns:
            The shipments.
        """
        shipment = models.Shipment
        stmt = sa.select(shipment).order_by(shipment.eta)
        if company_id is not None:
            stmt = stmt.where(shipment.company_id == company_id)
        if status:
            stmt = stmt.where(shipment.status == status)
        if exclude_statuses:
            stmt = stmt.where(shipment.status.not_in(list(exclude_statuses)))
        return await self._scalars(stmt)
