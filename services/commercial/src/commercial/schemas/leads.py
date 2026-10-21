"""API request and response models: leads."""

import datetime

import pydantic


class LeadCreate(pydantic.BaseModel):
    """A contact form submission from the website."""

    name: str = pydantic.Field(min_length=2, max_length=200)
    company: str = pydantic.Field(min_length=2, max_length=200)
    email: pydantic.EmailStr
    phone: str | None = pydantic.Field(default=None, max_length=50)
    origin: str | None = pydantic.Field(default=None, max_length=100)
    destination: str | None = pydantic.Field(default=None, max_length=100)
    teu_per_year: int | None = pydantic.Field(default=None, ge=0, le=100_000)
    message: str | None = pydantic.Field(default=None, max_length=4000)
    website: str | None = pydantic.Field(
        default=None, description="Honeypot field; must stay empty."
    )


class LeadOut(pydantic.BaseModel):
    """A lead, for ops."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    name: str
    company: str
    email: str
    phone: str | None
    origin: str | None
    destination: str | None
    teu_per_year: int | None
    message: str | None
    status: str
    created_at: datetime.datetime


class LeadUpdate(pydantic.BaseModel):
    """A lead's new status."""

    status: str = pydantic.Field(pattern="^(new|contacted|won|lost)$")


class LeadReceived(pydantic.BaseModel):
    """Acknowledgement of a lead submission."""

    status: str = "received"
