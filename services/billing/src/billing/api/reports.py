"""HTTP routes: reports."""

import fastapi

from billing import schemas
from billing.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get(
    "/reports/margin", response_model=schemas.MarginReport, tags=["reports"]
)
async def margin_report(
    user: dependencies.OpsUser, invoices: deps.Invoices
) -> schemas.MarginReport:
    """Gross profit per shipment and per TEU."""
    return await invoices.margin_report(user)
