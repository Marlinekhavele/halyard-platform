"""Settings of the Notifications service."""

import pydantic

from halyard_common import config


class Settings(config.ServiceSettings):
    """Notifications settings.

    Attributes:
        database_url: Read from ``NOTIFICATIONS_DATABASE_URL`` or
            ``DATABASE_URL``.
        smtp_host: SMTP server. Emails are only logged when empty.
        smtp_port: SMTP port.
        smtp_user: SMTP user name.
        smtp_password: SMTP password.
        smtp_starttls: Upgrade the connection with STARTTLS.
        mail_from: Sender address.
        app_url: Link added to the footer of every email.
    """

    service_name: str = "notifications"
    database_url: str = pydantic.Field(
        "sqlite+aiosqlite:///./notifications.db",
        validation_alias=pydantic.AliasChoices(
            "NOTIFICATIONS_DATABASE_URL", "DATABASE_URL"
        ),
    )
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    mail_from: str = "Halyard <hello@halyard.example>"
    app_url: str = "http://localhost:8080/app"
