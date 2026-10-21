"""HTTP API of the accounts service: one router per feature."""

import fastapi

from accounts.api import auth
from accounts.api import companies
from accounts.api import users

router = fastapi.APIRouter()
for _module in (
    auth,
    companies,
    users,
):
    router.include_router(_module.router)
