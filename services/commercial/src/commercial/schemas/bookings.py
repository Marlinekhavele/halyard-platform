"""API request and response models: bookings."""

import datetime
from typing import Self

import pydantic

from commercial import models
from commercial.schemas import quotes


class BookingOut(pydantic.BaseModel):
    """A booking."""

    id: str
    ref: str
    quote_id: str
    company_id: str
    requested_by_email: str
    status: str
    pol: str
    pod: str
    via_port: str | None
    carrier: str
    container_type: str
    quantity: int
    commodity: str
    incoterm: str
    gross_weight_kg: int
    cargo_value_cents: int
    supplier_name: str | None
    notes: str | None
    etd: datetime.date
    eta: datetime.date
    vessel: str | None
    voyage: str | None
    total_sell_cents: int
    total_cost_cents: int | None = None
    lines: list[quotes.LineOut]
    created_at: datetime.datetime
    confirmed_at: datetime.datetime | None
    cancel_reason: str | None

    @classmethod
    def from_model(cls, booking: models.Booking, show_cost: bool) -> Self:
        """Builds the response for a stored booking.

        Args:
            booking: The stored booking.
            show_cost: Whether to include cost prices.

        Returns:
            The response model.
        """
        fields = {
            name: getattr(booking, name)
            for name in cls.model_fields
            if name not in {"lines", "total_cost_cents"}
        }
        return cls(
            **fields,
            total_cost_cents=booking.total_cost_cents if show_cost else None,
            lines=[
                quotes.LineOut.from_dict(ln, show_cost) for ln in booking.lines
            ],
        )


class ConfirmBooking(pydantic.BaseModel):
    """Ops confirms carrier space, optionally with a changed schedule."""

    vessel: str = pydantic.Field(min_length=2, max_length=100)
    voyage: str = pydantic.Field(min_length=2, max_length=20)
    etd: datetime.date | None = None
    eta: datetime.date | None = None

    @pydantic.model_validator(mode="after")
    def _eta_after_etd(self) -> Self:
        if self.etd and self.eta and self.eta <= self.etd:
            raise ValueError("Arrival must be after departure.")
        return self


class CancelBooking(pydantic.BaseModel):
    """Why a booking is cancelled."""

    reason: str = pydantic.Field(min_length=3, max_length=300)
