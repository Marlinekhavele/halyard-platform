"""Stores shipment documents."""

from collections.abc import Collection, Sequence

import sqlalchemy as sa

from halyard_common import repository
from operations import models


class DocumentRepository(repository.Repository[models.Document]):
    """Stores shipment documents."""

    model = models.Document

    async def list_with_shipment_ref(
        self,
        company_id: str | None,
        statuses: Collection[str] | None = None,
    ) -> Sequence[tuple[models.Document, str]]:
        """Lists documents with their shipment reference, by due date.

        Documents without a due date come last.

        Args:
            company_id: Only this company's documents; None for all.
            statuses: Only documents in one of these statuses.

        Returns:
            ``(document, shipment_ref)`` pairs.
        """
        document = models.Document
        stmt = (
            sa.select(document, models.Shipment.ref)
            .join(models.Shipment)
            .order_by(
                document.due_date.is_(None), document.due_date, document.sort
            )
        )
        if company_id is not None:
            stmt = stmt.where(document.company_id == company_id)
        if statuses is not None:
            stmt = stmt.where(document.status.in_(list(statuses)))
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]
