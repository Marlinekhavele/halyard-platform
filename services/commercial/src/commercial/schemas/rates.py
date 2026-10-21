"""API request and response models: rates."""

import datetime

import pydantic


class RateOut(pydantic.BaseModel):
    """A rate, for ops."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    origin_region: str
    dest_region: str
    carrier: str
    service: str
    via_port: str | None
    container_type: str
    buy_cents: int
    sell_cents: int
    transit_days: int
    sailing_weekday: int
    co2_factor: float
    valid_until: datetime.date
    active: bool


class RateUpdate(pydantic.BaseModel):
    """Partial update of a rate."""

    buy_cents: int | None = pydantic.Field(default=None, ge=0)
    sell_cents: int | None = pydantic.Field(default=None, ge=0)
    transit_days: int | None = pydantic.Field(default=None, ge=1, le=90)
    valid_until: datetime.date | None = None
    active: bool | None = None


class SurchargeOut(pydantic.BaseModel):
    """A surcharge, for ops."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    code: str
    label: str
    basis: str
    sell_value: int
    cost_value: int
    min_sell_cents: int
    min_cost_cents: int
    container_type: str | None
    option: str | None
