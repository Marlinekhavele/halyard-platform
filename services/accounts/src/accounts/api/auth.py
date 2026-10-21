"""HTTP routes: auth."""

import fastapi

from accounts import schemas
from accounts import services
from accounts.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


def _token_response(sign_in: services.SignIn) -> schemas.TokenResponse:
    return schemas.TokenResponse(
        access_token=sign_in.access_token,
        user=schemas.UserOut.model_validate(sign_in.user),
        company=schemas.CompanyOut.model_validate(sign_in.company),
    )


@router.post(
    "/auth/register",
    response_model=schemas.TokenResponse,
    status_code=fastapi.status.HTTP_201_CREATED,
    tags=["auth"],
)
async def register(
    body: schemas.RegisterRequest, service: deps.Service
) -> schemas.TokenResponse:
    """A new importer signs up. Creates the company and its first admin."""
    sign_in = await service.register(
        body.company_name, body.name, body.email, body.password
    )
    return _token_response(sign_in)


@router.post("/auth/login", response_model=schemas.TokenResponse, tags=["auth"])
async def login(
    body: schemas.LoginRequest, service: deps.Service
) -> schemas.TokenResponse:
    """Signs in with email and password."""
    return _token_response(await service.login(body.email, body.password))


@router.get("/me", response_model=schemas.TokenResponse, tags=["auth"])
async def me(
    user: dependencies.CurrentUser, service: deps.Service
) -> schemas.TokenResponse:
    """Returns the signed-in user and company, with a refreshed token."""
    return _token_response(await service.refresh(user))
