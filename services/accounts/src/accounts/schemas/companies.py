"""API request and response models: companies."""

import pydantic


class CompanyOut(pydantic.BaseModel):
    """A company as returned by the API."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    name: str
    customer_number: str
    kind: str
    eori: str | None
    vat_id: str | None
    street: str | None
    postal_code: str | None
    city: str | None
    country: str


class CompanyUpdate(pydantic.BaseModel):
    """Partial update of the caller's company."""

    name: str | None = pydantic.Field(
        default=None, min_length=2, max_length=200
    )
    eori: str | None = pydantic.Field(
        default=None, pattern=r"^[A-Z]{2}[A-Z0-9]{1,15}$"
    )
    vat_id: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = pydantic.Field(
        default=None, min_length=2, max_length=2
    )
