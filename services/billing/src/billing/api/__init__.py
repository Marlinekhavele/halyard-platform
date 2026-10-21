"""HTTP API of the billing service: one router per feature."""

import fastapi

from billing.api import invoices
from billing.api import reports

router = fastapi.APIRouter()
for _module in (
    invoices,
    reports,
):
    router.include_router(_module.router)
