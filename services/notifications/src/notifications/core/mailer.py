"""Outgoing email."""

import abc
from email import message
import logging

from notifications.core import config

_log = logging.getLogger("halyard.notifications.mailer")


class Mailer(abc.ABC):
    """Sends plain-text emails."""

    @abc.abstractmethod
    async def send(self, to: list[str], subject: str, text: str) -> str:
        """Sends one email to several recipients.

        Implementations must not raise: an email failure must never block
        the event stream.

        Args:
            to: Recipient addresses.
            subject: The subject line.
            text: The body.

        Returns:
            ``sent``, ``logged``, ``failed`` or ``no recipients``.
        """


class SmtpMailer(Mailer):
    """Sends email over SMTP, or only logs it when no host is configured."""

    def __init__(self, settings: config.Settings) -> None:
        """Initialises the mailer.

        Args:
            settings: SMTP connection and sender settings.
        """
        self._settings = settings

    async def send(self, to: list[str], subject: str, text: str) -> str:
        """Sends one email; see ``Mailer.send``."""
        if not to:
            return "no recipients"
        settings = self._settings
        if not settings.smtp_host:
            _log.info(
                "email (not sent, SMTP not configured) to %s: %s",
                ", ".join(to),
                subject,
            )
            return "logged"
        import aiosmtplib  # pylint: disable=import-outside-toplevel

        msg = message.EmailMessage()
        msg["From"] = settings.mail_from
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(
            f"{text}\n\nOpen Halyard: {settings.app_url}\n\n"
            "— Halyard Freight, Berlin"
        )
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=settings.smtp_starttls,
            )
        except Exception as exc:  # pylint: disable=broad-except
            _log.warning("email to %s failed: %s", to, exc)
            return "failed"
        return "sent"
