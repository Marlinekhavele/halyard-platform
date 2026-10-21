"""Tests for the app factory, error mapping and request dependencies."""

import fastapi
import pytest

from halyard_common import config
from halyard_common import db
from halyard_common import dependencies
from halyard_common import errors
from halyard_common import service
from halyard_common import testing

router = fastapi.APIRouter()


@router.get("/whoami")
async def whoami(user: dependencies.CurrentUser) -> dict:
    return {"email": user.email}


@router.get("/ops-only")
async def ops_only(user: dependencies.OpsUser) -> dict:
    return {"email": user.email}


@router.get("/conflict")
async def conflict() -> dict:
    raise errors.ConflictError("Already done.")


@pytest.fixture(name="settings")
def fixture_settings(tmp_path) -> config.ServiceSettings:
    return config.ServiceSettings(
        service_name="probe",
        database_url=testing.sqlite_url(tmp_path),
        broker_url="memory://",
    )


@pytest.fixture(name="client")
async def fixture_client(settings):
    runtime = service.ServiceRuntime(settings, db.make_base().metadata)
    app = service.create_app(runtime, "Probe", "Test app", [router])
    async with testing.running_client(app) as client:
        yield client


async def test_health(client):
    r = await client.get("/health")

    assert r.json() == {"status": "ok", "service": "probe"}


async def test_service_errors_map_to_status_and_detail(client):
    r = await client.get("/conflict")

    assert r.status_code == 409
    assert r.json() == {"detail": "Already done."}


async def test_missing_token_is_401(client):
    r = await client.get("/whoami")

    assert r.status_code == 401
    assert r.json()["detail"] == "Sign in to continue."


async def test_valid_token_identifies_the_user(client, settings):
    user = testing.customer_user()

    r = await client.get(
        "/whoami", headers=testing.auth_headers(settings, user)
    )

    assert r.json() == {"email": user.email}


async def test_ops_dependency_rejects_customers(client, settings):
    customer = testing.auth_headers(settings, testing.customer_user())
    ops = testing.auth_headers(settings, testing.ops_user())

    assert (await client.get("/ops-only", headers=customer)).status_code == 403
    assert (await client.get("/ops-only", headers=ops)).status_code == 200


def test_cors_origin_list_ignores_blanks():
    settings = config.ServiceSettings(cors_origins=" http://a , ,http://b")

    assert settings.cors_origin_list == ["http://a", "http://b"]
