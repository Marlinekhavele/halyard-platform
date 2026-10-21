"""Fixtures for the Accounts tests."""

import pytest

from accounts import main
from accounts import models
from accounts import services
from accounts.core import config
from halyard_common import testing


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.Settings:
    return config.Settings(
        database_url=testing.sqlite_url(tmp_path, "accounts"),
        broker_url="memory://",
        seed_demo_data=False,
    )


@pytest.fixture(name="session")
async def fixture_session(settings):
    async with testing.database_session(
        settings.database_url, models.Base.metadata
    ) as session:
        yield session


@pytest.fixture(name="service")
def fixture_service(session, settings) -> services.AccountService:
    return services.AccountService(session, settings)


@pytest.fixture(name="client")
async def fixture_client(settings):
    async with testing.running_client(main.create_app(settings)) as client:
        yield client
