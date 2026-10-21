"""Fixtures for the Notifications tests."""

import pytest

from halyard_common import events
from halyard_common import testing
from notifications import main
from notifications import models
from notifications.core import config
from notifications.core import mailer
from notifications.events import handlers

CUSTOMER_EMAIL = "anna@customer.example"
OPS_EMAIL = "ops@halyard.example"


class FakeMailer(mailer.Mailer):
    """Records emails instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str, str]] = []

    async def send(self, to: list[str], subject: str, text: str) -> str:
        """Records the email; see ``Mailer.send``."""
        if not to:
            return "no recipients"
        self.sent.append((to, subject, text))
        return "sent"

    @property
    def subjects(self) -> list[str]:
        """Subjects of every sent email."""
        return [subject for _, subject, _ in self.sent]


def user_created(
    user_id: str, email: str, role: str, company_id: str
) -> events.UserCreated:
    """Builds a user-created event."""
    return events.UserCreated(
        user_id=user_id,
        company_id=company_id,
        company_name="Acme",
        email=email,
        name=email.split("@")[0].title(),
        role=role,
    )


def envelope(event_type: str, payload) -> events.EventEnvelope:
    """Wraps a payload into an envelope."""
    return events.EventEnvelope(
        type=event_type, source="test", data=payload.model_dump(mode="json")
    )


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.Settings:
    return config.Settings(
        database_url=testing.sqlite_url(tmp_path, "notifications"),
        broker_url="memory://",
    )


@pytest.fixture(name="fake_mailer")
def fixture_fake_mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture(name="session")
async def fixture_session(settings):
    async with testing.database_session(
        settings.database_url, models.Base.metadata
    ) as session:
        yield session


@pytest.fixture(name="event_handlers")
async def fixture_event_handlers(session, fake_mailer):
    """Handlers with one customer and one ops recipient registered."""
    event_handlers = handlers.EventHandlers(fake_mailer)
    for user in (
        user_created(
            "u1", CUSTOMER_EMAIL, "customer_admin", testing.CUSTOMER_COMPANY_ID
        ),
        user_created("u2", OPS_EMAIL, "ops", testing.OPS_COMPANY_ID),
    ):
        await event_handlers.on_user_created(
            session, envelope(events.EventType.USER_CREATED, user)
        )
    await session.commit()
    fake_mailer.sent.clear()
    return event_handlers


@pytest.fixture(name="client")
async def fixture_client(settings, fake_mailer):
    app = main.create_app(settings, mailer=fake_mailer)
    async with testing.running_client(app) as client:
        yield client
