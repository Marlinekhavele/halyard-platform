"""HTTP routes: leads."""

import fastapi

from commercial import schemas
from commercial.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.post(
    "/leads",
    response_model=schemas.LeadReceived,
    status_code=fastapi.status.HTTP_201_CREATED,
    tags=["leads"],
)
async def create_lead(
    body: schemas.LeadCreate, leads: deps.Leads
) -> schemas.LeadReceived:
    """Quote request from the public website. No sign-in needed."""
    await leads.create_lead(body)
    return schemas.LeadReceived()


@router.get("/leads", response_model=list[schemas.LeadOut], tags=["leads"])
async def list_leads(
    user: dependencies.OpsUser, leads: deps.Leads
) -> list[schemas.LeadOut]:
    """Lists website leads, newest first."""
    return [
        schemas.LeadOut.model_validate(ld)
        for ld in await leads.list_leads(user)
    ]


@router.patch(
    "/leads/{lead_id}", response_model=schemas.LeadOut, tags=["leads"]
)
async def update_lead(
    lead_id: str,
    body: schemas.LeadUpdate,
    user: dependencies.OpsUser,
    leads: deps.Leads,
) -> schemas.LeadOut:
    """Moves a lead through the sales pipeline."""
    lead = await leads.update_status(user, lead_id, body.status)
    return schemas.LeadOut.model_validate(lead)
