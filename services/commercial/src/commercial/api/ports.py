"""HTTP routes: ports."""

import fastapi

from commercial import schemas
from commercial.api import deps

router = fastapi.APIRouter()


@router.get("/ports", response_model=list[schemas.PortOut], tags=["reference"])
async def list_ports(quotes: deps.Quotes) -> list[schemas.PortOut]:
    """Lists every port we serve."""
    return [
        schemas.PortOut.model_validate(p) for p in await quotes.list_ports()
    ]
