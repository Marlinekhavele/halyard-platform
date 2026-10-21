"""Safe file names, upload limits, webhook auth and production settings."""

import pydantic
import pytest

from halyard_common import bus
from halyard_common import events
from halyard_common import testing
from operations.api import documents as documents_api
from operations.core import config
from operations.domain import shipping

from .. import conftest

PDF = b"%PDF-1.4\n"


@pytest.fixture(name="customer")
def fixture_customer(settings) -> dict[str, str]:
    return testing.auth_headers(settings, testing.customer_user())


@pytest.fixture(name="shipment")
async def fixture_shipment(client, customer):
    booking = conftest.booking_confirmed()
    await bus.InMemoryBus().publish(
        events.EventEnvelope(
            type=events.EventType.BOOKING_CONFIRMED,
            source="commercial",
            data=booking.model_dump(mode="json"),
        )
    )
    r = await client.get(f"/shipments/{booking.booking_ref}", headers=customer)
    return r.json()


@pytest.mark.parametrize(
    ("filename", "fallback"),
    [
        ("invoice.pdf", "invoice.pdf"),
        ("发票.pdf", "__.pdf"),
        (
            'Rechnung "final"\r\nX-Evil: 1.pdf',
            "Rechnung _final___X-Evil_ 1.pdf",
        ),
    ],
)
def test_content_disposition_is_always_a_safe_header(filename, fallback):
    header = documents_api.content_disposition(filename)

    header.encode("latin-1")  # HTTP headers must be Latin-1.
    assert "\r" not in header and "\n" not in header
    assert f'filename="{fallback}"' in header
    assert "filename*=UTF-8''" in header


async def test_download_with_a_non_latin_file_name(client, shipment, customer):
    doc = shipment["documents"][0]
    await client.post(
        f"/documents/{doc['id']}/upload",
        files={"file": ("发票 v2.pdf", PDF, "application/pdf")},
        headers=customer,
    )

    r = await client.get(f"/documents/{doc['id']}/file", headers=customer)

    assert r.status_code == 200
    assert r.content == PDF
    assert (
        "filename*=UTF-8''%E5%8F%91%E7%A5%A8%20v2.pdf"
        in (r.headers["content-disposition"])
    )


async def test_oversized_upload_is_rejected(
    client, shipment, customer, monkeypatch
):
    monkeypatch.setattr(shipping, "MAX_UPLOAD_BYTES", 4)
    doc = shipment["documents"][0]

    r = await client.post(
        f"/documents/{doc['id']}/upload",
        files={"file": ("big.pdf", b"%PDF-1.4 and more", "application/pdf")},
        headers=customer,
    )

    assert r.status_code == 413


async def test_webhook_without_token_is_401(client, shipment):
    r = await client.post(
        "/tracking/webhook",
        json={
            "container_number": shipment["containers"][0]["number"],
            "event": "GATE_IN",
            "occurred_at": "2026-10-07T09:00:00Z",
        },
    )

    assert r.status_code == 401


def test_production_refuses_the_dev_tracking_token():
    with pytest.raises(pydantic.ValidationError, match="TRACKING_WEBHOOK"):
        config.Settings(environment="production", jwt_secret="s" * 32)

    settings = config.Settings(
        environment="production",
        jwt_secret="s" * 32,
        tracking_webhook_token="a-real-shared-secret",
    )
    assert settings.is_protected
