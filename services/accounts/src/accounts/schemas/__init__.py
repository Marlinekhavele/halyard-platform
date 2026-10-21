"""Schemas of the accounts service, one module per feature."""

from accounts.schemas.auth import LoginRequest
from accounts.schemas.auth import RegisterRequest
from accounts.schemas.auth import TokenResponse
from accounts.schemas.companies import CompanyOut
from accounts.schemas.companies import CompanyUpdate
from accounts.schemas.users import InviteRequest
from accounts.schemas.users import UserOut

__all__ = [
    "CompanyOut",
    "CompanyUpdate",
    "InviteRequest",
    "LoginRequest",
    "RegisterRequest",
    "TokenResponse",
    "UserOut",
]
