"""HTTP routes: shipments."""

import fastapi

from halyard_common import dependencies
from operations import schemas
from operations.api import deps

router = fastapi.APIRouter()


@router.get(
    "/shipments",
    response_model=list[schemas.ShipmentSummary],
    tags=["shipments"],
)
async def list_shipments(
    user: dependencies.CurrentUser,
    shipments: deps.Shipments,
    status_filter: str | None = fastapi.Query(None, alias="status"),
    q: str | None = None,
    needs_action: bool | None = None,
) -> list[schemas.ShipmentSummary]:
    """Lists shipments, earliest arrival first."""
    return await shipments.list_shipments(user, status_filter, q, needs_action)


@router.get(
    "/shipments/{key}",
    response_model=schemas.ShipmentDetail,
    tags=["shipments"],
)
async def get_shipment(
    key: str, user: dependencies.CurrentUser, shipments: deps.Shipments
) -> schemas.ShipmentDetail:
    """Returns one shipment by id or reference."""
    shipment = await shipments.get_visible_shipment(user, key)
    return schemas.ShipmentDetail.from_model(shipment)


@router.get("/stats", response_model=schemas.ShipmentStats, tags=["shipments"])
async def stats(
    user: dependencies.CurrentUser, shipments: deps.Shipments
) -> schemas.ShipmentStats:
    """Returns headline numbers for the dashboard."""
    return await shipments.stats(user)
