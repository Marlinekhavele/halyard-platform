"""Stores invoices with their lines."""

from collections.abc import Sequence

import sqlalchemy as sa

from billing import models
from halyard_common import repository


class InvoiceRepository(repository.Repository[models.Invoice]):
    """Stores invoices with their lines."""

    model = models.Invoice

    async def get_by_booking(self, booking_id: str) -> models.Invoice | None:
        """Finds the invoice of a booking.

        Args:
            booking_id: The Commercial booking id.

        Returns:
            The invoice, or None.
        """
        return await self._scalar(
            sa.select(models.Invoice).where(
                models.Invoice.booking_id == booking_id
            )
        )

    async def list_recent(
        self,
        company_id: str | None,
        status: str | None = None,
        include_drafts: bool = True,
    ) -> Sequence[models.Invoice]:
        """Lists invoices, newest first.

        Args:
            company_id: Only this company's invoices; None for all.
            status: Only invoices in this status.
            include_drafts: Whether to include draft invoices.

        Returns:
            The invoices.
        """
        invoice = models.Invoice
        stmt = sa.select(invoice).order_by(invoice.created_at.desc())
        if company_id is not None:
            stmt = stmt.where(invoice.company_id == company_id)
        if not include_drafts:
            stmt = stmt.where(invoice.status != "draft")
        if status:
            stmt = stmt.where(invoice.status == status)
        return await self._scalars(stmt)

    async def list_billable(self) -> Sequence[models.Invoice]:
        """Lists every invoice that is not void, oldest first."""
        return await self._scalars(
            sa.select(models.Invoice)
            .where(models.Invoice.status != "void")
            .order_by(models.Invoice.created_at)
        )

    async def count_numbered_in_year(self, year: int) -> int:
        """Counts invoices already numbered in a year.

        Concurrent callers are serialised until commit, so two invoices never
        get the same number.

        Args:
            year: The calendar year.

        Returns:
            The count.
        """
        await repository.lock_sequence(self.session, f"invoice-number-{year}")
        return await self.count(models.Invoice.number.like(f"INV-{year}-%"))
