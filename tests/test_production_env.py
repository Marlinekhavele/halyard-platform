"""Tests for production environment preflight validation."""

import pathlib

from scripts import check_production_env

VALID_ENV = {
    "API_HOST": "api.halyard.test",
    "PUBLIC_URL": "https://app.halyard.test",
    "CORS_ORIGINS": "https://app.halyard.test",
    "ACME_EMAIL": "ops@halyard.test",
    "JWT_SECRET": "j" * 48,
    "POSTGRES_PASSWORD": "p" * 48,
    "RABBITMQ_PASSWORD": "r" * 48,
    "TRACKING_WEBHOOK_TOKEN": "t" * 48,
    "SMTP_HOST": "smtp.halyard.test",
    "SMTP_PORT": "587",
    "SMTP_USER": "halyard-smtp-user",
    "SMTP_PASSWORD": "s" * 48,
    "MAIL_FROM": "Halyard <hello@halyard.test>",
    "ENVIRONMENT": "production",
    "SEED_DEMO_DATA": "false",
}


def test_valid_production_values_pass() -> None:
    """Accepts well-formed production settings with HTTPS and unique secrets."""
    assert check_production_env.validate(VALID_ENV) == []


def test_development_placeholders_are_rejected() -> None:
    """Rejects example hosts, default secrets and development email settings."""
    example_path = (
        pathlib.Path(__file__).parents[1]
        / "deploy"
        / "production"
        / ".env.production.example"
    )
    values = check_production_env.read_env_file(example_path)

    errors = check_production_env.validate(values)

    assert errors
    assert any("JWT_SECRET" in error for error in errors)
    assert any("SMTP_HOST" in error for error in errors)
    assert any("API_HOST" in error or "PUBLIC_URL" in error for error in errors)
