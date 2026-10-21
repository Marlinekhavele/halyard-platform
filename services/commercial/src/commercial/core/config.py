"""Settings of the Commercial service."""

import pydantic

from halyard_common import config


class Settings(config.ServiceSettings):
    """Commercial settings.

    Attributes:
        database_url: Read from ``COMMERCIAL_DATABASE_URL`` or
            ``DATABASE_URL``.
        quote_validity_days: How long a saved quote can be booked.
    """

    service_name: str = "commercial"
    database_url: str = pydantic.Field(
        "sqlite+aiosqlite:///./commercial.db",
        validation_alias=pydantic.AliasChoices(
            "COMMERCIAL_DATABASE_URL", "DATABASE_URL"
        ),
    )
    quote_validity_days: int = 7
