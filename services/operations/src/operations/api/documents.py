"""HTTP routes: documents."""

import re
from urllib import parse

import fastapi
from fastapi import responses

from halyard_common import dependencies
from operations import schemas
from operations.api import deps
from operations.domain import shipping

router = fastapi.APIRouter()


def content_disposition(filename: str) -> str:
    """Builds an attachment header that is safe for any file name.

    HTTP headers are Latin-1, and quotes or line breaks in a name would break
    the header, so the plain ``filename`` gets an ASCII-only copy and the real
    name travels URL-encoded in ``filename*`` (RFC 6266 / RFC 5987).

    Args:
        filename: The original, user-supplied file name.

    Returns:
        The ``Content-Disposition`` header value.
    """
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).strip() or "document"
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{parse.quote(filename, safe='')}"
    )


@router.get(
    "/documents", response_model=list[schemas.DocumentOut], tags=["documents"]
)
async def list_documents(
    user: dependencies.CurrentUser,
    documents: deps.Documents,
    status_filter: str | None = fastapi.Query(None, alias="status"),
) -> list[schemas.DocumentOut]:
    """Lists documents; ``status=open`` shows what waits on the caller."""
    return [
        schemas.DocumentOut.from_model(doc, ref)
        for doc, ref in await documents.list_documents(user, status_filter)
    ]


@router.post(
    "/documents/{doc_id}/upload",
    response_model=schemas.DocumentOut,
    tags=["documents"],
)
async def upload_document(
    doc_id: str,
    user: dependencies.CurrentUser,
    documents: deps.Documents,
    file: fastapi.UploadFile = fastapi.File(...),
) -> schemas.DocumentOut:
    """Uploads a new version of a document."""
    # Read one byte past the limit: enough to reject oversized files without
    # loading an arbitrarily large upload into memory.
    data = await file.read(shipping.MAX_UPLOAD_BYTES + 1)
    doc, ref = await documents.upload(
        user, doc_id, file.filename, file.content_type, data
    )
    return schemas.DocumentOut.from_model(doc, ref)


@router.get("/documents/{doc_id}/file", tags=["documents"])
async def download_document(
    doc_id: str, user: dependencies.CurrentUser, documents: deps.Documents
) -> responses.Response:
    """Downloads a document's file."""
    stored = await documents.download(user, doc_id)
    return responses.Response(
        stored.data,
        media_type=stored.content_type,
        headers={"Content-Disposition": content_disposition(stored.filename)},
    )


@router.post(
    "/documents/{doc_id}/review",
    response_model=schemas.DocumentOut,
    tags=["documents"],
)
async def review_document(
    doc_id: str,
    body: schemas.ReviewDocument,
    user: dependencies.CurrentUser,
    documents: deps.Documents,
) -> schemas.DocumentOut:
    """Approves a document or sends it back with a note."""
    doc, ref = await documents.review(user, doc_id, body.approve, body.note)
    return schemas.DocumentOut.from_model(doc, ref)
