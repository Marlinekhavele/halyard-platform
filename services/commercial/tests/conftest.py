"""Fixtures for the Commercial tests."""

import datetime

import pytest

from commercial import main
from commercial import models
from commercial.core import config
from commercial.core import seed
from halyard_common import testing

TODAY = datetime.date(2026, 10, 5)  # A Monday.


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.Settings:
    return config.Settings(
        database_url=testing.sqlite_url(tmp_path, "commercial"),
        broker_url="memory://",
    )


@pytest.fixture(name="session")
async def fixture_session(settings):
    async with testing.database_session(
        settings.database_url, models.Base.metadata
    ) as session:
        await seed.add_reference_data(session, TODAY)
        await session.commit()
        yield session


@pytest.fixture(name="make_service")
def fixture_make_service(session, settings):
    """Returns a factory building any commercial service on a fixed date."""

    def make(cls, today: datetime.date = TODAY):
        return cls(session, settings, today=lambda: today)

    return make


@pytest.fixture(name="client")
async def fixture_client(settings):
    async with testing.running_client(main.create_app(settings)) as client:
        yield client
