"""The result of a successful sign-in."""

from collections.abc import Sequence
import dataclasses
import logging
from typing import Any

from sqlalchemy.ext import asyncio as sa_asyncio

from accounts import models
from accounts import repositories
from accounts.core import config
from accounts.core import passwords
from halyard_common import auth
from halyard_common import errors
from halyard_common import events
from halyard_common import outbox

_log = logging.getLogger("halyard.accounts")


@dataclasses.dataclass(frozen=True)
class SignIn:
    """The result of a successful sign-in.

    Attributes:
        access_token: The signed JWT.
        user: The signed-in user.
        company: The user's company.
    """

    access_token: str
    user: models.User
    company: models.Company


def as_current_user(user: models.User) -> auth.CurrentUser:
    """Converts a stored user into the identity carried in tokens.

    Args:
        user: The stored user.

    Returns:
        The token identity.
    """
    return auth.CurrentUser(
        id=user.id,
        company_id=user.company_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


class AccountService:
    """Sign-up, sign-in, company and team management."""

    def __init__(
        self, session: sa_asyncio.AsyncSession, settings: config.Settings
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request.
            settings: The service settings.
        """
        self._session = session
        self._settings = settings
        self.companies = repositories.CompanyRepository(session)
        self.users = repositories.UserRepository(session)
        self.outbox = outbox.OutboxRepository(
            session, models.OutboxEvent, settings.service_name
        )

    # ---- Sign-in -----------------------------------------------------------

    async def register(
        self, company_name: str, name: str, email: str, password: str
    ) -> SignIn:
        """Signs up a new company with its first admin user.

        Args:
            company_name: Legal name of the company.
            name: The admin's name.
            email: The admin's email.
            password: The admin's password.

        Returns:
            The new admin, signed in.

        Raises:
            errors.ConflictError: The email is already registered.
        """
        email = email.lower()
        if await self.users.get_by_email(email):
            raise errors.ConflictError(
                "An account with this email already exists. Sign in instead."
            )
        company = await self.companies.add(
            models.Company(
                name=company_name.strip(),
                customer_number=await self.companies.next_customer_number(),
            )
        )
        user = await self.users.add(
            models.User(
                company_id=company.id,
                email=email,
                name=name.strip(),
                password_hash=passwords.hash_password(password),
                role="customer_admin",
            )
        )
        self.outbox.add(
            events.EventType.COMPANY_REGISTERED,
            events.CompanyRegistered(
                company_id=company.id,
                name=company.name,
                customer_number=company.customer_number,
            ),
        )
        self.stage_user_created(user, company)
        await self._session.commit()
        return self._sign_in(user, company)

    async def login(self, email: str, password: str) -> SignIn:
        """Signs a user in with email and password.

        Args:
            email: The user's email.
            password: The user's password.

        Returns:
            The signed-in user.

        Raises:
            errors.AuthenticationError: Unknown email, wrong password or
                inactive account.
        """
        user = await self.users.get_by_email(email.lower())
        if not user:
            reason = "unknown_email"
        elif not user.is_active:
            reason = "inactive"
        elif not passwords.verify_password(password, user.password_hash):
            reason = "wrong_password"
        else:
            reason = None
        if reason:
            # Never log the password or the address that was tried.
            _log.warning(
                "sign-in failed",
                extra={"reason": reason, "user_id": user.id if user else None},
            )
            raise errors.AuthenticationError("Email or password is incorrect.")
        company = await self.companies.get(user.company_id)
        return self._sign_in(user, company)

    async def refresh(self, current: auth.CurrentUser) -> SignIn:
        """Reloads the caller and issues a fresh token.

        Args:
            current: The caller.

        Returns:
            The signed-in user with a new token.

        Raises:
            errors.AuthenticationError: The account no longer exists or is
                inactive.
        """
        user = await self.users.get(current.id)
        if not user or not user.is_active:
            raise errors.AuthenticationError(
                "This account is no longer active."
            )
        company = await self.companies.get(user.company_id)
        return self._sign_in(user, company)

    # ---- Companies ---------------------------------------------------------

    async def get_own_company(
        self, current: auth.CurrentUser
    ) -> models.Company:
        """Returns the caller's company.

        Args:
            current: The caller.

        Returns:
            The company.

        Raises:
            errors.NotFoundError: The company no longer exists.
        """
        return await self.get_company(current, current.company_id)

    async def update_own_company(
        self, current: auth.CurrentUser, changes: dict[str, Any]
    ) -> models.Company:
        """Updates details of the caller's company.

        Args:
            current: The caller; must be a company admin.
            changes: Field names and new values.

        Returns:
            The updated company.

        Raises:
            errors.PermissionDeniedError: The caller is not a company admin.
        """
        if not current.is_company_admin:
            raise errors.PermissionDeniedError(
                "Only a company admin can change company details."
            )
        company = await self.get_own_company(current)
        for field, value in changes.items():
            setattr(company, field, value)
        await self._session.commit()
        return company

    async def list_companies(
        self, current: auth.CurrentUser
    ) -> Sequence[models.Company]:
        """Lists every company. Ops only.

        Args:
            current: The caller.

        Returns:
            All companies by name.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
        """
        auth.require_ops(current)
        return await self.companies.list_by_name()

    async def get_company(
        self, current: auth.CurrentUser, company_id: str
    ) -> models.Company:
        """Returns a company the caller may see.

        Args:
            current: The caller.
            company_id: The company.

        Returns:
            The company.

        Raises:
            errors.NotFoundError: The company does not exist or is not
                visible to the caller.
        """
        company = (
            await self.companies.get(company_id)
            if current.can_see_company(company_id)
            else None
        )
        if not company:
            raise errors.NotFoundError("Company not found.")
        return company

    # ---- Team --------------------------------------------------------------

    async def list_team(
        self, current: auth.CurrentUser
    ) -> Sequence[models.User]:
        """Lists the users of the caller's company.

        Args:
            current: The caller.

        Returns:
            The team, by name.
        """
        return await self.users.list_for_company(current.company_id)

    async def invite(
        self,
        current: auth.CurrentUser,
        name: str,
        email: str,
        password: str,
        role: str,
    ) -> models.User:
        """Adds a user to the caller's company.

        Args:
            current: The caller; must be a company admin.
            name: The new user's name.
            email: The new user's email.
            password: The new user's initial password.
            role: ``customer`` or ``customer_admin``.

        Returns:
            The new user.

        Raises:
            errors.PermissionDeniedError: The caller is not a company admin.
            errors.ConflictError: The email is already in use.
        """
        if not current.is_company_admin:
            raise errors.PermissionDeniedError(
                "Only a company admin can add team members."
            )
        email = email.lower()
        if await self.users.get_by_email(email):
            raise errors.ConflictError("Someone already uses this email.")
        company = await self.get_own_company(current)
        user = await self.users.add(
            models.User(
                company_id=company.id,
                email=email,
                name=name,
                password_hash=passwords.hash_password(password),
                role=role,
            )
        )
        self.stage_user_created(user, company)
        await self._session.commit()
        return user

    # ---- Helpers -----------------------------------------------------------

    def stage_user_created(
        self, user: models.User, company: models.Company
    ) -> None:
        """Stages an ``accounts.user_created`` event.

        Args:
            user: The new user.
            company: The user's company.
        """
        self.outbox.add(
            events.EventType.USER_CREATED,
            events.UserCreated(
                user_id=user.id,
                company_id=company.id,
                company_name=company.name,
                email=user.email,
                name=user.name,
                role=user.role,
            ),
        )

    def _sign_in(self, user: models.User, company: models.Company) -> SignIn:
        token = auth.create_access_token(self._settings, as_current_user(user))
        return SignIn(access_token=token, user=user, company=company)
