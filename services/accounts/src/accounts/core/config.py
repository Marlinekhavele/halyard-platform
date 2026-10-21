"""Settings of the Accounts service."""

import pydantic

from halyard_common import config


class Settings(config.ServiceSettings):
    """Accounts settings.

    Attributes:
        database_url: Read from ``ACCOUNTS_DATABASE_URL`` or ``DATABASE_URL``.
    """

    service_name: str = "accounts"
    database_url: str = pydantic.Field(
        "sqlite+aiosqlite:///./accounts.db",
        validation_alias=pydantic.AliasChoices(
            "ACCOUNTS_DATABASE_URL", "DATABASE_URL"
        ),
    )
