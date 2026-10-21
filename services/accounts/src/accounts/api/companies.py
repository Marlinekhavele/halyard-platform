"""HTTP routes: companies."""

import fastapi

from accounts import schemas
from accounts.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get(
    "/companies/me", response_model=schemas.CompanyOut, tags=["companies"]
)
async def my_company(
    user: dependencies.CurrentUser, service: deps.Service
) -> schemas.CompanyOut:
    """Returns the caller's company."""
    return schemas.CompanyOut.model_validate(
        await service.get_own_company(user)
    )


@router.patch(
    "/companies/me", response_model=schemas.CompanyOut, tags=["companies"]
)
async def update_my_company(
    body: schemas.CompanyUpdate,
    user: dependencies.CurrentUser,
    service: deps.Service,
) -> schemas.CompanyOut:
    """Updates the caller's company. Company admins only."""
    company = await service.update_own_company(
        user, body.model_dump(exclude_unset=True)
    )
    return schemas.CompanyOut.model_validate(company)


@router.get(
    "/companies", response_model=list[schemas.CompanyOut], tags=["companies"]
)
async def list_companies(
    user: dependencies.OpsUser, service: deps.Service
) -> list[schemas.CompanyOut]:
    """Lists every company. Ops only."""
    return [
        schemas.CompanyOut.model_validate(c)
        for c in await service.list_companies(user)
    ]


@router.get(
    "/companies/{company_id}",
    response_model=schemas.CompanyOut,
    tags=["companies"],
)
async def get_company(
    company_id: str, user: dependencies.CurrentUser, service: deps.Service
) -> schemas.CompanyOut:
    """Returns one company the caller may see."""
    return schemas.CompanyOut.model_validate(
        await service.get_company(user, company_id)
    )
