"""JWT authentication shared by every service.

The Accounts service issues tokens; every other service only verifies them.
Tokens carry the user's company, so each service can enforce that customers
see only their own company's data.

Production note: move to asymmetric keys (RS256 and a JWKS endpoint on
Accounts, or Keycloak) so that services hold only the public key.
"""

import datetime

import jwt
import pydantic

from halyard_common import config
from halyard_common import db
from halyard_common import errors

OPS_ROLES = frozenset({"ops", "admin"})
CUSTOMER_ROLES = frozenset({"customer_admin", "customer"})
COMPANY_ADMIN_ROLES = frozenset({"customer_admin", "admin"})


class CurrentUser(pydantic.BaseModel):
    """The authenticated caller, as described by their access token.

    Attributes:
        id: User id.
        company_id: The company the user belongs to.
        email: Sign-in email address.
        name: Display name.
        role: One of ``OPS_ROLES`` or ``CUSTOMER_ROLES``.
    """

    id: str
    company_id: str
    email: str
    name: str
    role: str

    @property
    def is_ops(self) -> bool:
        """Whether the user belongs to the Halyard operations team."""
        return self.role in OPS_ROLES

    @property
    def is_company_admin(self) -> bool:
        """Whether the user may manage their company and its team."""
        return self.role in COMPANY_ADMIN_ROLES

    def can_see_company(self, company_id: str) -> bool:
        """Checks whether the user may see data owned by a company.

        Args:
            company_id: The owning company.

        Returns:
            True for ops users and for members of that company.
        """
        return self.is_ops or self.company_id == company_id


def create_access_token(
    settings: config.ServiceSettings, user: CurrentUser
) -> str:
    """Signs an access token for a user.

    Args:
        settings: Provides the signing secret, algorithm, issuer and lifetime.
        user: The user the token identifies.

    Returns:
        The encoded JWT.
    """
    now = db.utcnow()
    expires = now + datetime.timedelta(minutes=settings.access_token_minutes)
    claims = {
        "sub": user.id,
        "cid": user.company_id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(
        claims, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def decode_access_token(
    settings: config.ServiceSettings, token: str
) -> CurrentUser:
    """Verifies an access token and returns the user it identifies.

    Args:
        settings: Provides the verification secret, algorithm and issuer.
        token: The encoded JWT.

    Returns:
        The authenticated user.

    Raises:
        errors.AuthenticationError: The token is expired or invalid.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise errors.AuthenticationError(
            "Your session has expired. Sign in again."
        ) from exc
    except jwt.PyJWTError as exc:
        raise errors.AuthenticationError("Invalid access token.") from exc
    return CurrentUser(
        id=claims["sub"],
        company_id=claims["cid"],
        email=claims["email"],
        name=claims["name"],
        role=claims["role"],
    )


def require_ops(user: CurrentUser) -> None:
    """Ensures the user belongs to the operations team.

    Args:
        user: The caller.

    Raises:
        errors.PermissionDeniedError: The user is not an ops user.
    """
    if not user.is_ops:
        raise errors.PermissionDeniedError(
            "Only the Halyard operations team can do this."
        )
