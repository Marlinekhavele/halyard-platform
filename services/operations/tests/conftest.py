"""Fixtures for the Operations tests."""

import datetime

import pytest

from halyard_common import events
from halyard_common import testing
from operations import main
from operations import models
from operations.core import config
from operations.core import storage

NOW = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.UTC)
ETD = datetime.date(2026, 10, 10)
ETA = datetime.date(2026, 11, 12)


class MemoryStorage(storage.FileStorage):
    """In-memory file storage for tests."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, key: str, data: bytes) -> None:
        """Stores the file in memory."""
        self.files[key] = data

    async def read(self, key: str) -> bytes:
        """Returns the stored file."""
        return self.files[key]

    async def delete(self, key: str) -> None:
        """Forgets the file."""
        self.files.pop(key, None)


def booking_confirmed(**overrides) -> events.BookingConfirmed:
    """Builds a confirmed-booking event for a two-container shipment."""
    data = {
        "booking_id": "booking-1",
        "booking_ref": "HLY-26-00001",
        "company_id": testing.CUSTOMER_COMPANY_ID,
        "contact_email": "anna@customer.example",
        "pol": "CNSHA",
        "pod": "DEHAM",
        "via": "SGSIN",
        "pol_name": "Shanghai",
        "pod_name": "Hamburg",
        "via_name": "Singapore",
        "carrier": "Hapag-Lloyd",
        "vessel": "Elbe Meridian",
        "voyage": "052W",
        "etd": ETD,
        "eta": ETA,
        "container_type": "40HC",
        "quantity": 2,
        "commodity": "Bicycle components",
        "incoterm": "FOB",
        "gross_weight_kg": 18_400,
        "cargo_value_cents": 8_600_000,
        "lines": [
            {
                "code": "OCEAN",
                "label": "Ocean",
                "sell_cents": 100,
                "cost_cents": 90,
            }
        ],
        **overrides,
    }
    return events.BookingConfirmed(**data)


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.Settings:
    return config.Settings(
        database_url=testing.sqlite_url(tmp_path, "operations"),
        broker_url="memory://",
        document_storage_dir=str(tmp_path / "documents"),
        tracking_webhook_token="secret-token",
    )


@pytest.fixture(name="session")
async def fixture_session(settings):
    async with testing.database_session(
        settings.database_url, models.Base.metadata
    ) as session:
        yield session


@pytest.fixture(name="file_storage")
def fixture_file_storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture(name="make_service")
def fixture_make_service(session, settings, file_storage):
    """Returns a factory building any operations service at a fixed time."""

    def make(cls, now: datetime.datetime = NOW):
        if cls.__name__ == "DocumentService":
            return cls(session, settings, file_storage, now=lambda: now)
        return cls(session, settings, now=lambda: now)

    return make


@pytest.fixture(name="app")
def fixture_app(settings, file_storage):
    return main.create_app(settings, storage=file_storage)


@pytest.fixture(name="client")
async def fixture_client(app):
    async with testing.running_client(app) as client:
        yield client
