"""Tests for production guards and sequence locking."""

import pydantic
import pytest

from halyard_common import config
from halyard_common import db
from halyard_common import repository
from halyard_common import testing

STRONG_SECRET = "s" * config.MIN_SECRET_LENGTH


@pytest.mark.parametrize("environment", ["production", "staging", "Production"])
def test_protected_environments_refuse_the_dev_secret(environment):
    with pytest.raises(pydantic.ValidationError, match="JWT_SECRET"):
        config.ServiceSettings(environment=environment)


def test_protected_environments_refuse_short_secrets():
    with pytest.raises(pydantic.ValidationError, match="at least 32"):
        config.ServiceSettings(environment="production", jwt_secret="short")


def test_protected_environments_accept_a_strong_secret():
    settings = config.ServiceSettings(
        environment="production", jwt_secret=STRONG_SECRET
    )

    assert settings.is_protected


def test_development_keeps_working_with_defaults():
    settings = config.ServiceSettings(environment="development")

    assert not settings.is_protected
    assert settings.jwt_secret == config.DEV_JWT_SECRET


async def test_lock_sequence_is_a_no_op_on_sqlite(tmp_path):
    database = db.Database(testing.sqlite_url(tmp_path))
    async with database.sessionmaker() as session:
        await repository.lock_sequence(session, "invoice-number")

        assert not session.in_transaction()
    await database.dispose()
