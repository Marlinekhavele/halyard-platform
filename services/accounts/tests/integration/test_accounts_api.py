"""HTTP tests for the Accounts API."""

import pytest

from accounts import main
from halyard_common import demo
from halyard_common import testing

REGISTRATION = {
    "company_name": "Acme GmbH",
    "name": "Anna Keller",
    "email": "anna@acme.example",
    "password": "password123",
}


def _bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_register_login_and_me(client):
    r = await client.post("/auth/register", json=REGISTRATION)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["company"]["customer_number"] == "HLY-20501"
    assert "password_hash" not in body["user"]

    r = await client.post(
        "/auth/login",
        json={"email": REGISTRATION["email"], "password": "password123"},
    )
    assert r.status_code == 200

    r = await client.get("/me", headers=_bearer(r))
    assert r.json()["user"]["email"] == REGISTRATION["email"]


async def test_duplicate_registration_is_409(client):
    await client.post("/auth/register", json=REGISTRATION)

    r = await client.post("/auth/register", json=REGISTRATION)

    assert r.status_code == 409


async def test_wrong_password_is_401(client):
    await client.post("/auth/register", json=REGISTRATION)

    r = await client.post(
        "/auth/login",
        json={"email": REGISTRATION["email"], "password": "not-it"},
    )

    assert r.status_code == 401
    assert r.json()["detail"] == "Email or password is incorrect."


async def test_short_password_is_rejected_by_validation(client):
    r = await client.post(
        "/auth/register", json={**REGISTRATION, "password": "short"}
    )

    assert r.status_code == 422


async def test_company_and_team_endpoints(client):
    headers = _bearer(await client.post("/auth/register", json=REGISTRATION))

    r = await client.patch(
        "/companies/me", json={"eori": "DE123456"}, headers=headers
    )
    assert r.json()["eori"] == "DE123456"

    r = await client.post(
        "/users",
        json={
            "name": "Ben",
            "email": "ben@acme.example",
            "password": "password123",
        },
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["role"] == "customer"

    r = await client.get("/users", headers=headers)
    assert [u["name"] for u in r.json()] == ["Anna Keller", "Ben"]


async def test_company_list_is_ops_only(client, settings):
    await client.post("/auth/register", json=REGISTRATION)
    customer = testing.auth_headers(settings, testing.customer_user())
    ops = testing.auth_headers(settings, testing.ops_user())

    assert (await client.get("/companies", headers=customer)).status_code == 403
    r = await client.get("/companies", headers=ops)
    assert [c["name"] for c in r.json()] == ["Acme GmbH"]


@pytest.fixture(name="seeded_client")
async def fixture_seeded_client(settings):
    seeded = settings.model_copy(update={"seed_demo_data": True})
    async with testing.running_client(main.create_app(seeded)) as client:
        yield client


async def test_demo_users_are_seeded(seeded_client):
    for email, password in [
        (demo.DEMO_EMAIL, demo.DEMO_PASSWORD),
        (demo.OPS_EMAIL, demo.OPS_PASSWORD),
    ]:
        r = await seeded_client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        assert r.status_code == 200, email
