"""Tests for accounts.services."""

import pytest
import sqlalchemy as sa

from accounts import models
from accounts import services
from halyard_common import auth
from halyard_common import errors
from halyard_common import events
from halyard_common import testing


async def _outbox_types(session) -> list[str]:
    rows = await session.scalars(
        sa.select(models.OutboxEvent.type).order_by(
            models.OutboxEvent.created_at
        )
    )
    return list(rows)


async def _register(service, email="anna@acme.example"):
    return await service.register("Acme GmbH ", " Anna", email, "password123")


async def test_register_creates_company_admin_and_events(service, session):
    sign_in = await _register(service, "Anna@Acme.example")

    assert sign_in.company.name == "Acme GmbH"
    assert sign_in.company.customer_number == "HLY-20501"
    assert sign_in.user.email == "anna@acme.example"
    assert sign_in.user.name == "Anna"
    assert sign_in.user.role == "customer_admin"
    assert sign_in.user.password_hash != "password123"
    assert await _outbox_types(session) == [
        events.EventType.COMPANY_REGISTERED,
        events.EventType.USER_CREATED,
    ]


async def test_register_token_identifies_the_new_user(service, settings):
    sign_in = await _register(service)

    user = auth.decode_access_token(settings, sign_in.access_token)

    assert user.id == sign_in.user.id
    assert user.company_id == sign_in.company.id


async def test_register_rejects_duplicate_email(service):
    await _register(service)

    with pytest.raises(errors.ConflictError):
        await _register(service, "ANNA@acme.example")


async def test_login_accepts_correct_password_case_insensitively(service):
    await _register(service)

    sign_in = await service.login("ANNA@acme.example", "password123")

    assert sign_in.user.email == "anna@acme.example"


async def test_login_rejects_wrong_password(service):
    await _register(service)

    with pytest.raises(errors.AuthenticationError):
        await service.login("anna@acme.example", "wrong-password")


async def test_login_rejects_unknown_and_inactive_users(service, session):
    sign_in = await _register(service)
    sign_in.user.is_active = False
    await session.commit()

    with pytest.raises(errors.AuthenticationError):
        await service.login("anna@acme.example", "password123")
    with pytest.raises(errors.AuthenticationError):
        await service.login("nobody@acme.example", "password123")


async def test_refresh_rejects_deleted_account(service):
    ghost = testing.customer_user()

    with pytest.raises(errors.AuthenticationError):
        await service.refresh(ghost)


async def test_only_company_admins_update_company(service):
    sign_in = await _register(service)
    admin = services.as_current_user(sign_in.user)
    member = admin.model_copy(update={"role": "customer"})

    company = await service.update_own_company(admin, {"city": "Berlin"})

    assert company.city == "Berlin"
    with pytest.raises(errors.PermissionDeniedError):
        await service.update_own_company(member, {"city": "Hamburg"})


async def test_get_company_hides_other_companies(service):
    mine = await _register(service)
    other = await _register(service, "olaf@other.example")
    me = services.as_current_user(mine.user)

    assert (await service.get_company(me, mine.company.id)).id == (
        mine.company.id
    )
    with pytest.raises(errors.NotFoundError):
        await service.get_company(me, other.company.id)
    ops_view = await service.get_company(testing.ops_user(), other.company.id)
    assert ops_view.id == other.company.id


async def test_list_companies_is_ops_only(service):
    await _register(service)

    assert len(await service.list_companies(testing.ops_user())) == 1
    with pytest.raises(errors.PermissionDeniedError):
        await service.list_companies(testing.customer_user())


async def test_invite_adds_team_member(service, session):
    sign_in = await _register(service)
    admin = services.as_current_user(sign_in.user)

    user = await service.invite(
        admin, "Ben", "Ben@Acme.example", "password123", "customer"
    )

    assert user.email == "ben@acme.example"
    assert user.company_id == sign_in.company.id
    team = [u.name for u in await service.list_team(admin)]
    assert team == ["Anna", "Ben"]
    assert (await _outbox_types(session)).count(
        events.EventType.USER_CREATED
    ) == 2


async def test_invite_requires_admin_and_unique_email(service):
    sign_in = await _register(service)
    admin = services.as_current_user(sign_in.user)
    member = admin.model_copy(update={"role": "customer"})

    with pytest.raises(errors.PermissionDeniedError):
        await service.invite(
            member, "Ben", "ben@acme.example", "password123", "customer"
        )
    with pytest.raises(errors.ConflictError):
        await service.invite(
            admin, "Anna 2", "anna@acme.example", "password123", "customer"
        )


async def test_failed_sign_in_is_logged_without_secrets(service, caplog):
    await _register(service)

    with pytest.raises(errors.AuthenticationError):
        await service.login("anna@acme.example", "wrong-password")

    [record] = [r for r in caplog.records if r.message == "sign-in failed"]
    assert record.levelname == "WARNING"
    assert record.reason == "wrong_password"
    assert record.user_id
    logged = str(record.__dict__)
    assert "wrong-password" not in logged
    assert "anna@acme.example" not in logged
