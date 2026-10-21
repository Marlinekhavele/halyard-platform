"""HTTP routes: tracking."""

from typing import Annotated

import fastapi

from halyard_common import dependencies
from operations import schemas
from operations.api import deps

router = fastapi.APIRouter()


@router.post(
    "/tracking/webhook",
    response_model=schemas.TrackingResult,
    tags=["tracking"],
)
async def tracking_webhook(
    body: schemas.TrackingWebhook,
    tracking: deps.Tracking,
    x_tracking_token: Annotated[str | None, fastapi.Header()] = None,
) -> schemas.TrackingResult:
    """Receives container events from the tracking data provider."""
    outcome = await tracking.receive_webhook(x_tracking_token, body)
    return schemas.TrackingResult(
        shipment_ref=outcome.shipment.ref,
        status=outcome.shipment.status,
        applied=outcome.applied,
    )


@router.post(
    "/shipments/{key}/simulate",
    response_model=schemas.ShipmentDetail,
    tags=["tracking"],
)
async def simulate(
    key: str,
    body: schemas.SimulateStep,
    user: dependencies.OpsUser,
    tracking: deps.Tracking,
) -> schemas.ShipmentDetail:
    """Demo helper: moves the shipment on as if every container reported."""
    shipment = await tracking.simulate(user, key, body)
    return schemas.ShipmentDetail.from_model(shipment)
