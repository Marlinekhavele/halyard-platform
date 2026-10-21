"""API request and response models: auth."""

import pydantic

from accounts.schemas import companies
from accounts.schemas import users


class RegisterRequest(pydantic.BaseModel):
    """Sign-up of a new importer company and its first admin."""

    company_name: str = pydantic.Field(min_length=2, max_length=200)
    name: str = pydantic.Field(min_length=2, max_length=200)
    email: pydantic.EmailStr
    password: str = pydantic.Field(min_length=8, max_length=128)


class LoginRequest(pydantic.BaseModel):
    """Email and password sign-in."""

    email: pydantic.EmailStr
    password: str


class TokenResponse(pydantic.BaseModel):
    """An access token with the signed-in user and their company."""

    access_token: str
    token_type: str = "bearer"
    user: users.UserOut
    company: companies.CompanyOut
