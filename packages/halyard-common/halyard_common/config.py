"""Settings shared by every service."""

from typing import Self

import pydantic
import pydantic_settings

DEV_JWT_SECRET = "dev-only-secret-change-me-please-32b"
MIN_SECRET_LENGTH = 32
# Environments where development defaults must never be used.
PROTECTED_ENVIRONMENTS = frozenset({"production", "staging"})


class ServiceSettings(pydantic_settings.BaseSettings):
    """Settings every service shares. Each service subclasses this.

    Values come from environment variables (for example ``DATABASE_URL`` and
    ``BROKER_URL``) or a local ``.env`` file.

    Attributes:
        service_name: Name used for logs, queues and event sources.
        environment: Deployment environment label.
        database_url: SQLAlchemy async URL of the service's own database.
        auto_create_tables: Create tables on startup. Use migrations in
            production instead.
        broker_url: ``memory://`` for one process, ``amqp://...`` for
            RabbitMQ.
        events_exchange: Name of the RabbitMQ topic exchange.
        jwt_secret: Shared secret for signing and verifying access tokens.
        jwt_algorithm: JWT signing algorithm.
        jwt_issuer: Expected ``iss`` claim.
        access_token_minutes: Access token lifetime.
        root_path: Path prefix when served behind the gateway.
        cors_origins: Comma-separated list of allowed browser origins.
        seed_demo_data: Create demo records on startup.
        outbox_poll_seconds: How often the outbox relay looks for events.
        otel_exporter_otlp_endpoint: Enables tracing when set.
        log_level: Minimum log level, for example ``INFO`` or ``DEBUG``.
        log_json: Log one JSON object per line instead of readable text.
    """

    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    service_name: str = "service"
    environment: str = "development"

    database_url: str = "sqlite+aiosqlite:///./dev.db"
    auto_create_tables: bool = True

    broker_url: str = "memory://"
    events_exchange: str = "halyard.events"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "halyard-accounts"
    access_token_minutes: int = 60 * 12

    root_path: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    seed_demo_data: bool = True
    outbox_poll_seconds: float = 0.5

    otel_exporter_otlp_endpoint: str | None = None

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def is_protected(self) -> bool:
        """Whether this is a production-like environment."""
        return self.environment.lower() in PROTECTED_ENVIRONMENTS

    @pydantic.model_validator(mode="after")
    def _require_real_secret(self) -> Self:
        if self.is_protected and (
            self.jwt_secret == DEV_JWT_SECRET
            or len(self.jwt_secret) < MIN_SECRET_LENGTH
        ):
            raise ValueError(
                "JWT_SECRET must be set to a random value of at least"
                f" {MIN_SECRET_LENGTH} characters in {self.environment}."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """The allowed CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
