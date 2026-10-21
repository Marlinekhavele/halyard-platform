"""HTTP routes: bookings."""

import fastapi

from commercial import schemas
from commercial.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get(
    "/bookings", response_model=list[schemas.BookingOut], tags=["bookings"]
)
async def list_bookings(
    user: dependencies.CurrentUser,
    bookings: deps.Bookings,
    status_filter: str | None = fastapi.Query(None, alias="status"),
) -> list[schemas.BookingOut]:
    """Lists bookings the caller may see."""
    return [
        schemas.BookingOut.from_model(b, user.is_ops)
        for b in await bookings.list_bookings(user, status_filter)
    ]


@router.get(
    "/bookings/{booking_id}",
    response_model=schemas.BookingOut,
    tags=["bookings"],
)
async def get_booking(
    booking_id: str, user: dependencies.CurrentUser, bookings: deps.Bookings
) -> schemas.BookingOut:
    """Returns one booking."""
    booking = await bookings.get_booking(user, booking_id)
    return schemas.BookingOut.from_model(booking, user.is_ops)


@router.post(
    "/bookings/{booking_id}/confirm",
    response_model=schemas.BookingOut,
    tags=["bookings"],
)
async def confirm_booking(
    booking_id: str,
    body: schemas.ConfirmBooking,
    user: dependencies.OpsUser,
    bookings: deps.Bookings,
) -> schemas.BookingOut:
    """Ops confirms space with the carrier."""
    booking = await bookings.confirm(user, booking_id, body)
    return schemas.BookingOut.from_model(booking, user.is_ops)


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=schemas.BookingOut,
    tags=["bookings"],
)
async def cancel_booking(
    booking_id: str,
    body: schemas.CancelBooking,
    user: dependencies.CurrentUser,
    bookings: deps.Bookings,
) -> schemas.BookingOut:
    """Cancels a booking."""
    booking = await bookings.cancel(user, booking_id, body.reason)
    return schemas.BookingOut.from_model(booking, user.is_ops)
