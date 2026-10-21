"""API request and response models: documents."""

import datetime
from typing import Self

import pydantic

from operations import models


class DocumentOut(pydantic.BaseModel):
    """A shipment document."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    shipment_id: str
    shipment_ref: str | None = None
    doc_type: str
    label: str
    status: str
    due_date: datetime.date | None
    note: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    checks: list[dict] | None
    uploaded_by: str | None
    uploaded_at: datetime.datetime | None
    reviewed_by: str | None
    reviewed_at: datetime.datetime | None

    @classmethod
    def from_model(cls, document: models.Document, shipment_ref: str) -> Self:
        """Builds the response for a stored document.

        Args:
            document: The stored document.
            shipment_ref: Reference of the document's shipment.

        Returns:
            The response model.
        """
        return cls.model_validate(document).model_copy(
            update={"shipment_ref": shipment_ref}
        )


class ReviewDocument(pydantic.BaseModel):
    """Approve a document, or send it back with a note."""

    approve: bool
    note: str | None = pydantic.Field(default=None, max_length=500)
