"""Recipients, notifications and the feeds users read."""

from collections.abc import Sequence

from sqlalchemy.ext import asyncio as sa_asyncio

from halyard_common import auth
from halyard_common import db
from halyard_common import events
from notifications import models
from notifications import repositories
from notifications.core import mailer as mailer_lib

MAX_LIST_LIMIT = 100


WELCOME_SUBJECT = "Welcome to Halyard"


class NotificationService:
    """Recipients, notifications and the feeds users read."""

    def __init__(
        self, session: sa_asyncio.AsyncSession, mailer: mailer_lib.Mailer
    ) -> None:
        """Initialises the service.

        Args:
            session: The unit of work for this request or event.
            mailer: Sends emails.
        """
        self._session = session
        self._mailer = mailer
        self.recipients = repositories.RecipientRepository(session)
        self.notifications = repositories.NotificationRepository(session)

    async def register_recipient(self, user: events.UserCreated) -> None:
        """Adds or updates the local copy of a user; welcomes new customers.

        Does not commit; the event consumer owns the transaction.

        Args:
            user: The created user.
        """
        existing = await self.recipients.get(user.user_id)
        if existing:
            existing.email = user.email
            existing.name = user.name
            existing.role = user.role
            return
        await self.recipients.add(
            models.Recipient(
                user_id=user.user_id,
                company_id=user.company_id,
                company_name=user.company_name,
                email=user.email,
                name=user.name,
                role=user.role,
            )
        )
        if user.role not in auth.OPS_ROLES:
            await self._mailer.send(
                [user.email],
                WELCOME_SUBJECT,
                f"Hi {user.name},\n\nyour Halyard account for"
                f" {user.company_name} is ready. Get an instant all-in quote"
                " for your next container in under a minute.",
            )

    async def is_ops_email(self, email: str | None) -> bool:
        """Checks whether an address belongs to an ops user.

        Args:
            email: The address, or None.

        Returns:
            True for known ops users.
        """
        if email is None:
            return False
        return await self.recipients.role_of(email) in auth.OPS_ROLES

    async def notify(
        self,
        event_type: str,
        *,
        audience: str,
        company_id: str | None,
        kind: str,
        title: str,
        body: str,
        link: str | None = None,
    ) -> models.Notification:
        """Emails an audience and stores the in-app notification.

        Does not commit; the event consumer owns the transaction.

        Args:
            event_type: The event that caused the notification.
            audience: ``customer`` (the company's users) or ``ops``.
            company_id: The company concerned.
            kind: ``info``, ``success``, ``warning`` or ``action``.
            title: Subject line and headline.
            body: The message.
            link: Where the client should take the reader.

        Returns:
            The stored notification.
        """
        if audience == "ops":
            to = await self.recipients.ops_emails()
        else:
            to = await self.recipients.customer_emails(company_id)
        status = await self._mailer.send(to, title, body)
        notification = models.Notification(
            audience=audience,
            company_id=company_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            event_type=event_type,
            emailed_to=", ".join(to) or None,
            email_status=status,
        )
        return await self.notifications.add(notification)

    async def list_for(
        self, user: auth.CurrentUser, limit: int
    ) -> Sequence[models.Notification]:
        """Returns a user's newest notifications.

        Args:
            user: The reader.
            limit: Maximum number, capped at ``MAX_LIST_LIMIT``.

        Returns:
            The notifications, newest first.
        """
        return await self.notifications.list_for(
            user, min(limit, MAX_LIST_LIMIT)
        )

    async def mark_all_read(self, user: auth.CurrentUser) -> None:
        """Marks a user's whole feed as read.

        Args:
            user: The reader.
        """
        await self.notifications.mark_all_read(user, db.utcnow())
        await self._session.commit()
