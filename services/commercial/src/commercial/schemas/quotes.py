"""API request and response models: quotes."""

import datetime
from typing import Self

import pydantic

from commercial import models
from commercial.domain import pricing

CONTAINER_PATTERN = "^(20DV|40DV|40HC|40RF)$"


INCOTERM_PATTERN = "^(EXW|FCA|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)$"


class QuoteCreate(pydantic.BaseModel):
    """A price request."""

    pol: str = pydantic.Field(
        min_length=5, max_length=5, description="Port of loading, UN/LOCODE"
    )
    pod: str = pydantic.Field(
        min_length=5, max_length=5, description="Port of discharge, UN/LOCODE"
    )
    container_type: str = pydantic.Field(pattern=CONTAINER_PATTERN)
    quantity: int = pydantic.Field(ge=1, le=50)
    ready_date: datetime.date
    incoterm: str = pydantic.Field(default="FOB", pattern=INCOTERM_PATTERN)
    commodity: str = pydantic.Field(
        default="General cargo", min_length=2, max_length=200
    )
    cargo_value_cents: int = pydantic.Field(default=0, ge=0)
    customs: bool = False
    trucking: bool = False
    insurance: bool = False

    @pydantic.model_validator(mode="after")
    def _different_ports(self) -> Self:
        if self.pol == self.pod:
            raise ValueError(
                "Port of loading and port of discharge must be different."
            )
        return self


class LineOut(pydantic.BaseModel):
    """One charge. ``cost_cents`` is only shown to ops."""

    code: str
    label: str
    quantity: int
    sell_cents: int
    cost_cents: int | None = None

    @classmethod
    def from_dict(cls, line: dict, show_cost: bool) -> Self:
        """Builds a line from its stored JSON form.

        Args:
            line: The stored line.
            show_cost: Whether to include the cost price.

        Returns:
            The response model.
        """
        return cls(
            **{**line, "cost_cents": line["cost_cents"] if show_cost else None}
        )


class OptionOut(pydantic.BaseModel):
    """One priced sailing. ``id`` is None for unsaved estimates."""

    id: str | None = None
    label: str
    carrier: str
    service: str
    via_port: str | None
    etd: datetime.date
    eta: datetime.date
    transit_days: int
    co2_kg: int
    total_sell_cents: int
    total_cost_cents: int | None = None
    lines: list[LineOut]

    @classmethod
    def from_model(cls, option: models.QuoteOption, show_cost: bool) -> Self:
        """Builds the response for a stored option.

        Args:
            option: The stored option.
            show_cost: Whether to include cost prices.

        Returns:
            The response model.
        """
        return cls(
            id=option.id,
            label=option.label,
            carrier=option.carrier,
            service=option.service,
            via_port=option.via_port,
            etd=option.etd,
            eta=option.eta,
            transit_days=option.transit_days,
            co2_kg=option.co2_kg,
            total_sell_cents=option.total_sell_cents,
            total_cost_cents=option.total_cost_cents if show_cost else None,
            lines=[LineOut.from_dict(ln, show_cost) for ln in option.lines],
        )

    @classmethod
    def from_priced(cls, option: pricing.PricedOption) -> Self:
        """Builds the public response for an unsaved estimate.

        Args:
            option: The priced option.

        Returns:
            The response model, without any cost prices.
        """
        return cls(
            label=option.label,
            carrier=option.rate.carrier,
            service=option.rate.service,
            via_port=option.rate.via_port,
            etd=option.etd,
            eta=option.eta,
            transit_days=option.transit_days,
            co2_kg=option.co2_kg,
            total_sell_cents=option.total_sell_cents,
            lines=[
                LineOut(
                    code=ln.code,
                    label=ln.label,
                    quantity=ln.quantity,
                    sell_cents=ln.sell_cents,
                )
                for ln in option.lines
            ],
        )


class QuoteOut(pydantic.BaseModel):
    """A saved quote."""

    id: str
    ref: str
    company_id: str
    created_by_email: str
    pol: str
    pod: str
    container_type: str
    quantity: int
    ready_date: datetime.date
    incoterm: str
    commodity: str
    cargo_value_cents: int
    customs: bool
    trucking: bool
    insurance: bool
    status: str
    valid_until: datetime.date
    created_at: datetime.datetime
    options: list[OptionOut]

    @classmethod
    def from_model(
        cls, quote: models.Quote, show_cost: bool, today: datetime.date
    ) -> Self:
        """Builds the response for a stored quote.

        Args:
            quote: The stored quote.
            show_cost: Whether to include cost prices.
            today: Reference date for expiry.

        Returns:
            The response model.
        """
        fields = {
            name: getattr(quote, name)
            for name in cls.model_fields
            if name not in {"options", "status"}
        }
        return cls(
            **fields,
            status=quote.status_on(today),
            options=[OptionOut.from_model(o, show_cost) for o in quote.options],
        )


class EstimateOut(pydantic.BaseModel):
    """A public, indicative price."""

    pol: str
    pod: str
    container_type: str
    quantity: int
    options: list[OptionOut]
    note: str = (
        "Indicative all-in price. Sign up to book and lock this price for 7"
        " days."
    )


class AcceptOption(pydantic.BaseModel):
    """Details the customer adds when booking an option."""

    gross_weight_kg: int = pydantic.Field(ge=100, le=30_000 * 50)
    supplier_name: str | None = pydantic.Field(default=None, max_length=200)
    notes: str | None = pydantic.Field(default=None, max_length=2000)
