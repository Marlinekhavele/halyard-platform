"""API request and response models: users."""

import pydantic


class UserOut(pydantic.BaseModel):
    """A user as returned by the API. Never includes the password hash."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    id: str
    company_id: str
    email: str
    name: str
    role: str
    is_active: bool


class InviteRequest(pydantic.BaseModel):
    """A company admin adds a team member."""

    name: str = pydantic.Field(min_length=2, max_length=200)
    email: pydantic.EmailStr
    password: str = pydantic.Field(min_length=8, max_length=128)
    role: str = pydantic.Field(
        default="customer", pattern="^(customer|customer_admin)$"
    )
