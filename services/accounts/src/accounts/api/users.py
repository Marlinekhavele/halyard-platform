"""HTTP routes: users."""

import fastapi

from accounts import schemas
from accounts.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get("/users", response_model=list[schemas.UserOut], tags=["users"])
async def list_team(
    user: dependencies.CurrentUser, service: deps.Service
) -> list[schemas.UserOut]:
    """Lists the caller's team."""
    return [
        schemas.UserOut.model_validate(u) for u in await service.list_team(user)
    ]


@router.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=fastapi.status.HTTP_201_CREATED,
    tags=["users"],
)
async def invite_user(
    body: schemas.InviteRequest,
    user: dependencies.CurrentUser,
    service: deps.Service,
) -> schemas.UserOut:
    """Adds a team member. Company admins only."""
    new_user = await service.invite(
        user, body.name, body.email, body.password, body.role
    )
    return schemas.UserOut.model_validate(new_user)
