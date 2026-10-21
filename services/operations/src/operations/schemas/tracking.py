"""API request and response models: tracking."""

import datetime

import pydantic


class TrackingWebhook(pydantic.BaseModel):
    """Normalised tracking event.

    Write a small adapter per provider (Vizion, Terminal49, ...) that maps
    their payload to this shape.
    """

    container_number: str = pydantic.Field(min_length=11, max_length=13)
    event: str
    occurred_at: datetime.datetime
    location: str | None = None
    description: str | None = None
    new_eta: datetime.date | None = None
    reason: str | None = None


class SimulateStep(pydantic.BaseModel):
    """A simulated tracking event for every container of a shipment."""

    event: str | None = pydantic.Field(
        default=None, description="Leave empty to move to the next milestone."
    )
    occurred_at: datetime.datetime | None = None
    new_eta: datetime.date | None = None
    reason: str | None = None


class TrackingResult(pydantic.BaseModel):
    """What a tracking event changed."""

    shipment_ref: str
    status: str
    applied: str
