"""HTTP API of the operations service: one router per feature."""

import fastapi

from operations.api import documents
from operations.api import shipments
from operations.api import tracking

router = fastapi.APIRouter()
for _module in (
    tracking,
    shipments,
    documents,
):
    router.include_router(_module.router)
