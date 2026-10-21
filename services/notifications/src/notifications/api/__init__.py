"""HTTP API of the notifications service: one router per feature."""

import fastapi

from notifications.api import notifications

router = fastapi.APIRouter()
for _module in (notifications,):
    router.include_router(_module.router)
