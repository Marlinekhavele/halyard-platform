"""HTTP routes: notifications."""

import fastapi

from halyard_common import dependencies
from notifications import schemas
from notifications.api import deps

router = fastapi.APIRouter()


@router.get(
    "/notifications",
    response_model=list[schemas.NotificationOut],
    tags=["notifications"],
)
async def list_notifications(
    user: dependencies.CurrentUser,
    notifications: deps.Notifications,
    limit: int = fastapi.Query(30, ge=1, le=100),
) -> list[schemas.NotificationOut]:
    """Lists the caller's newest notifications."""
    return [
        schemas.NotificationOut.model_validate(n)
        for n in await notifications.list_for(user, limit)
    ]


@router.post(
    "/notifications/read-all",
    response_model=schemas.StatusOut,
    tags=["notifications"],
)
async def read_all(
    user: dependencies.CurrentUser, notifications: deps.Notifications
) -> schemas.StatusOut:
    """Marks every notification in the caller's feed as read."""
    await notifications.mark_all_read(user)
    return schemas.StatusOut()
