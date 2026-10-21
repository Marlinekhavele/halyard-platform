"""HTTP routes: quotes."""

import fastapi

from commercial import schemas
from commercial.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.post(
    "/quotes/estimate", response_model=schemas.EstimateOut, tags=["quotes"]
)
async def estimate(
    body: schemas.QuoteCreate, quotes: deps.Quotes
) -> schemas.EstimateOut:
    """Public, indicative price for the website. Nothing is saved."""
    options = await quotes.price(body)
    return schemas.EstimateOut(
        pol=body.pol,
        pod=body.pod,
        container_type=body.container_type,
        quantity=body.quantity,
        options=[schemas.OptionOut.from_priced(o) for o in options],
    )


@router.post(
    "/quotes",
    response_model=schemas.QuoteOut,
    status_code=fastapi.status.HTTP_201_CREATED,
    tags=["quotes"],
)
async def create_quote(
    body: schemas.QuoteCreate,
    user: dependencies.CurrentUser,
    quotes: deps.Quotes,
) -> schemas.QuoteOut:
    """Prices a request and saves it as a bookable quote."""
    quote = await quotes.create_quote(user, body)
    return schemas.QuoteOut.from_model(quote, user.is_ops, quotes.today())


@router.get("/quotes", response_model=list[schemas.QuoteOut], tags=["quotes"])
async def list_quotes(
    user: dependencies.CurrentUser,
    quotes: deps.Quotes,
    limit: int = fastapi.Query(50, ge=1, le=200),
) -> list[schemas.QuoteOut]:
    """Lists the newest quotes the caller may see."""
    today = quotes.today()
    return [
        schemas.QuoteOut.from_model(q, user.is_ops, today)
        for q in await quotes.list_quotes(user, limit)
    ]


@router.get(
    "/quotes/{quote_id}", response_model=schemas.QuoteOut, tags=["quotes"]
)
async def get_quote(
    quote_id: str, user: dependencies.CurrentUser, quotes: deps.Quotes
) -> schemas.QuoteOut:
    """Returns one quote."""
    quote = await quotes.get_quote(user, quote_id)
    return schemas.QuoteOut.from_model(quote, user.is_ops, quotes.today())


@router.post(
    "/quotes/{quote_id}/options/{option_id}/book",
    response_model=schemas.BookingOut,
    status_code=fastapi.status.HTTP_201_CREATED,
    tags=["bookings"],
)
async def book_option(
    quote_id: str,
    option_id: str,
    body: schemas.AcceptOption,
    user: dependencies.CurrentUser,
    quotes: deps.Quotes,
) -> schemas.BookingOut:
    """Customer accepts one option; ops then confirms it with the carrier."""
    booking = await quotes.book_option(user, quote_id, option_id, body)
    return schemas.BookingOut.from_model(booking, user.is_ops)
