"""HTTP routes: rates."""

import fastapi

from commercial import schemas
from commercial import services
from commercial.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get("/rates", response_model=list[schemas.RateOut], tags=["rates"])
async def list_rates(
    user: dependencies.OpsUser,
    rates: deps.Rates,
    origin_region: str | None = None,
    dest_region: str | None = None,
    container_type: str | None = None,
) -> list[schemas.RateOut]:
    """Lists rates, optionally filtered by lane and container type."""
    return [
        schemas.RateOut.model_validate(r)
        for r in await rates.list_rates(
            user, origin_region, dest_region, container_type
        )
    ]


@router.patch(
    "/rates/{rate_id}", response_model=schemas.RateOut, tags=["rates"]
)
async def update_rate(
    rate_id: str,
    body: schemas.RateUpdate,
    user: dependencies.OpsUser,
    rates: deps.Rates,
) -> schemas.RateOut:
    """Changes a rate's prices, transit time, validity or status."""
    rate = await rates.update_rate(
        user, rate_id, body.model_dump(exclude_unset=True)
    )
    return schemas.RateOut.model_validate(rate)


@router.get(
    "/surcharges", response_model=list[schemas.SurchargeOut], tags=["rates"]
)
async def list_surcharges(
    user: dependencies.OpsUser, rates: deps.Rates
) -> list[schemas.SurchargeOut]:
    """Lists surcharges."""
    return [
        schemas.SurchargeOut.model_validate(s)
        for s in await rates.list_surcharges(user)
    ]


@router.get("/vessels", tags=["rates"])
async def vessel_suggestions(
    user: dependencies.OpsUser, carrier: str
) -> list[str]:
    """Suggests vessel names for a carrier."""
    del user  # Only required for authorisation.
    return services.RateService.vessel_suggestions(carrier)
