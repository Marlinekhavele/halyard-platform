"""Tests for halyard_common.auth."""

import pytest

from halyard_common import auth
from halyard_common import config
from halyard_common import errors
from halyard_common import testing


@pytest.fixture(name="settings")
def fixture_settings() -> config.ServiceSettings:
    return config.ServiceSettings(jwt_secret="x" * 40)


def test_token_round_trip(settings):
    user = testing.customer_user()

    token = auth.create_access_token(settings, user)

    assert auth.decode_access_token(settings, token) == user


def test_expired_token_is_rejected(settings):
    expired = settings.model_copy(update={"access_token_minutes": -1})
    token = auth.create_access_token(expired, testing.customer_user())

    with pytest.raises(errors.AuthenticationError, match="expired"):
        auth.decode_access_token(settings, token)


def test_token_signed_with_other_secret_is_rejected(settings):
    other = config.ServiceSettings(jwt_secret="y" * 40)
    token = auth.create_access_token(other, testing.customer_user())

    with pytest.raises(errors.AuthenticationError, match="Invalid"):
        auth.decode_access_token(settings, token)


def test_token_from_other_issuer_is_rejected(settings):
    other = settings.model_copy(update={"jwt_issuer": "someone-else"})
    token = auth.create_access_token(other, testing.customer_user())

    with pytest.raises(errors.AuthenticationError):
        auth.decode_access_token(settings, token)


@pytest.mark.parametrize(
    ("role", "is_ops", "is_admin"),
    [
        ("ops", True, False),
        ("admin", True, True),
        ("customer_admin", False, True),
        ("customer", False, False),
    ],
)
def test_role_properties(role, is_ops, is_admin):
    user = testing.make_user(role=role)

    assert user.is_ops is is_ops
    assert user.is_company_admin is is_admin


def test_customers_only_see_their_own_company():
    user = testing.customer_user("company-a")

    assert user.can_see_company("company-a")
    assert not user.can_see_company("company-b")


def test_ops_see_every_company():
    assert testing.ops_user().can_see_company("any-company")


def test_require_ops_rejects_customers():
    auth.require_ops(testing.ops_user())
    with pytest.raises(errors.PermissionDeniedError):
        auth.require_ops(testing.customer_user())
