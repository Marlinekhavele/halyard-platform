"""Document uploads, downloads and reviews."""

from collections.abc import Sequence
import dataclasses

from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import auth
from halyard_common import db
from halyard_common import errors
from halyard_common import events
from operations import models
from operations.core import config
from operations.core import storage as storage_lib
from operations.domain import shipping
from operations.services import base


@dataclasses.dataclass(frozen=True)
class DocumentFile:
    """A stored document file ready to download.

    Attributes:
        data: The file content.
        filename: The original file name.
        content_type: The MIME type.
    """

    data: bytes
    filename: str
    content_type: str


class DocumentService(base.OperationsService):
    """Document uploads, downloads and reviews."""

    def __init__(
        self,
        session: sa_asyncio.AsyncSession,
        settings: config.Settings,
        storage: storage_lib.FileStorage,
        now: base.Clock = db.utcnow,
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request.
            settings: The service settings.
            storage: Where document files are kept.
            now: Returns the current UTC time; replaceable in tests.
        """
        super().__init__(session, settings, now)
        self._storage = storage

    async def get_document(
        self, user: auth.CurrentUser, doc_id: str
    ) -> models.Document:
        """Returns a document the caller may see.

        Args:
            user: The caller.
            doc_id: The document.

        Returns:
            The document.

        Raises:
            errors.NotFoundError: The document does not exist or is not
                visible.
        """
        doc = await self.documents.get(doc_id)
        if not doc or not user.can_see_company(doc.company_id):
            raise errors.NotFoundError("Document not found.")
        return doc

    async def list_documents(
        self, user: auth.CurrentUser, status: str | None
    ) -> Sequence[tuple[models.Document, str]]:
        """Lists documents the caller may see.

        Args:
            user: The caller.
            status: A status, or ``open`` for documents waiting on the
                caller: uploads to check for ops, documents to provide or
                approve for customers.

        Returns:
            ``(document, shipment_ref)`` pairs by due date.
        """
        if status == "open":
            statuses = (
                {"uploaded"} if user.is_ops else shipping.OPEN_FOR_CUSTOMER
            )
        elif status:
            statuses = {status}
        else:
            statuses = None
        return await self.documents.list_with_shipment_ref(
            base.company_scope(user), statuses
        )

    async def upload(
        self,
        user: auth.CurrentUser,
        doc_id: str,
        filename: str | None,
        content_type: str | None,
        data: bytes,
    ) -> tuple[models.Document, str]:
        """Stores a new version of a document.

        Customer uploads go to ops for checking; ops uploads are shared with
        the customer for approval.

        Args:
            user: The caller.
            doc_id: The document.
            filename: Original file name.
            content_type: Declared MIME type.
            data: The file content.

        Returns:
            The document and its shipment reference.

        Raises:
            errors.NotFoundError: The document does not exist or is not
                visible.
            errors.ConflictError: The document is approved, or not yet due
                for a customer.
            errors.UnsupportedMediaTypeError: The file type is not accepted.
            errors.PayloadTooLargeError: The file is too large.
        """
        doc = await self.get_document(user, doc_id)
        if doc.status == "approved":
            raise errors.ConflictError("This document is already approved.")
        if doc.status == "not_due" and not user.is_ops:
            raise errors.ConflictError(
                "We'll share this document with you when it is ready."
            )
        content_type = content_type or "application/octet-stream"
        if content_type not in shipping.ALLOWED_UPLOAD_TYPES:
            raise errors.UnsupportedMediaTypeError(
                "Upload a PDF, image, Excel, Word or CSV file."
            )
        if len(data) > shipping.MAX_UPLOAD_BYTES:
            raise errors.PayloadTooLargeError("Files can be up to 20 MB.")

        if doc.storage_key:
            await self._storage.delete(doc.storage_key)
        key = f"{doc.company_id}/{doc.shipment_id}/{doc.id}-{db.new_id()[:8]}"
        await self._storage.save(key, data)
        doc.filename = (filename or "document")[:255]
        doc.storage_key = key
        doc.content_type = content_type
        doc.size_bytes = len(data)
        doc.checks = shipping.basic_document_checks(content_type, data)
        doc.uploaded_by = user.email
        doc.uploaded_at = self._now()
        doc.reviewed_by = None
        doc.reviewed_at = None
        doc.note = None
        doc.status = "review" if user.is_ops else "uploaded"
        shipment = await self.shipments.get(doc.shipment_id)
        self.outbox.add(
            events.EventType.DOCUMENT_UPLOADED,
            events.DocumentUploaded(
                document_id=doc.id,
                shipment_id=doc.shipment_id,
                shipment_ref=shipment.ref,
                company_id=doc.company_id,
                doc_type=doc.doc_type,
                label=doc.label,
                uploaded_by_email=user.email,
            ),
        )
        await self._session.commit()
        return doc, shipment.ref

    async def download(
        self, user: auth.CurrentUser, doc_id: str
    ) -> DocumentFile:
        """Returns the stored file of a document.

        Args:
            user: The caller.
            doc_id: The document.

        Returns:
            The file.

        Raises:
            errors.NotFoundError: The document does not exist, is not
                visible or has no file.
        """
        doc = await self.get_document(user, doc_id)
        if not doc.storage_key:
            raise errors.NotFoundError("No file has been uploaded yet.")
        return DocumentFile(
            data=await self._storage.read(doc.storage_key),
            filename=doc.filename or "document",
            content_type=doc.content_type or "application/octet-stream",
        )

    async def review(
        self,
        user: auth.CurrentUser,
        doc_id: str,
        approve: bool,
        note: str | None,
    ) -> tuple[models.Document, str]:
        """Approves a document or sends it back.

        Ops review customer uploads; customers review documents ops shared.

        Args:
            user: The caller.
            doc_id: The document.
            approve: Approve (True) or send back (False).
            note: What needs to change; required when sending back.

        Returns:
            The document and its shipment reference.

        Raises:
            errors.NotFoundError: The document does not exist or is not
                visible.
            errors.PermissionDeniedError: A customer tried to review their
                own upload.
            errors.ConflictError: The document is not awaiting this
                caller's review.
            errors.InvalidRequestError: Sent back without a note.
        """
        doc = await self.get_document(user, doc_id)
        if doc.status == "uploaded" and not user.is_ops:
            raise errors.PermissionDeniedError(
                "Our operations team checks this document."
            )
        if doc.status == "review" and user.is_ops:
            raise errors.ConflictError(
                "Waiting for the customer to approve this document."
            )
        if doc.status not in {"uploaded", "review"}:
            raise errors.ConflictError(
                "There is nothing to review on this document."
            )
        if not approve and not note:
            raise errors.InvalidRequestError(
                "Say what needs to change so it can be fixed."
            )
        shared_by_ops = doc.status == "review"
        if approve:
            doc.status = "approved"
        else:
            doc.status = "not_due" if shared_by_ops else "required"
        doc.note = note
        doc.reviewed_by = user.email
        doc.reviewed_at = self._now()
        shipment = await self.shipments.get(doc.shipment_id)
        self.outbox.add(
            events.EventType.DOCUMENT_REVIEWED,
            events.DocumentReviewed(
                document_id=doc.id,
                shipment_id=doc.shipment_id,
                shipment_ref=shipment.ref,
                company_id=doc.company_id,
                label=doc.label,
                approved=approve,
                note=note,
                reviewed_by_email=user.email,
            ),
        )
        await self._session.commit()
        return doc, shipment.ref
