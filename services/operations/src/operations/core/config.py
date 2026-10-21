"""Settings of the Operations service."""

from typing import Self

import pydantic

from halyard_common import config

DEV_TRACKING_TOKEN = "dev-tracking-token"


class Settings(config.ServiceSettings):
    """Operations settings.

    Attributes:
        database_url: Read from ``OPERATIONS_DATABASE_URL`` or
            ``DATABASE_URL``.
        document_storage_dir: Where uploaded documents are stored.
        tracking_webhook_token: Shared secret the tracking provider sends in
            the ``X-Tracking-Token`` header.
    """

    service_name: str = "operations"
    database_url: str = pydantic.Field(
        "sqlite+aiosqlite:///./operations.db",
        validation_alias=pydantic.AliasChoices(
            "OPERATIONS_DATABASE_URL", "DATABASE_URL"
        ),
    )
    document_storage_dir: str = "./storage"
    tracking_webhook_token: str = DEV_TRACKING_TOKEN

    @pydantic.model_validator(mode="after")
    def _require_real_tracking_token(self) -> Self:
        if (
            self.is_protected
            and self.tracking_webhook_token == DEV_TRACKING_TOKEN
        ):
            raise ValueError(
                f"TRACKING_WEBHOOK_TOKEN must be changed in {self.environment}."
            )
        return self
