"""HTTP API of the commercial service: one router per feature."""

import fastapi

from commercial.api import bookings
from commercial.api import leads
from commercial.api import ports
from commercial.api import quotes
from commercial.api import rates

router = fastapi.APIRouter()
for _module in (
    ports,
    quotes,
    bookings,
    rates,
    leads,
):
    router.include_router(_module.router)
