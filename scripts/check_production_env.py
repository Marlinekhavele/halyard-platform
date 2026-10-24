"""Validates a production environment file before Compose interpolation."""

import argparse
import pathlib
import re
import urllib.parse

MIN_SECRET_LENGTH = 32
REQUIRED_VALUES = (
    "API_HOST",
    "PUBLIC_URL",
    "CORS_ORIGINS",
    "ACME_EMAIL",
    "JWT_SECRET",
    "POSTGRES_PASSWORD",
    "RABBITMQ_PASSWORD",
    "TRACKING_WEBHOOK_TOKEN",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "MAIL_FROM",
)


def read_env_file(path: pathlib.Path) -> dict[str, str]:
    """Reads basic KEY=VALUE entries from an environment file.

    Args:
        path: Environment file to read.

    Returns:
        Mapping from environment variable name to value.

    Raises:
        ValueError: If a non-comment line is not a KEY=VALUE entry.
    """
    values = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Line {line_number} is not KEY=VALUE.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def validate(values: dict[str, str]) -> list[str]:
    """Returns actionable validation errors for an MVP production config.

    Args:
        values: Environment variables parsed from the target file.

    Returns:
        Human-readable validation errors; an empty list means checks passed.
    """
    errors = []
    for key in REQUIRED_VALUES:
        if not values.get(key, "").strip():
            errors.append(f"{key} is required.")

    for key in (
        "JWT_SECRET",
        "POSTGRES_PASSWORD",
        "RABBITMQ_PASSWORD",
        "TRACKING_WEBHOOK_TOKEN",
    ):
        value = values.get(key, "")
        if len(value) < MIN_SECRET_LENGTH:
            errors.append(
                f"{key} must contain at least {MIN_SECRET_LENGTH} characters."
            )
        if value.lower() in {
            "dev-only-secret-change-me-please-32b",
            "dev-tracking-token",
            "change_me",
            "change-me",
            "halyard",
            "password",
        }:
            errors.append(
                f"{key} still contains a known development placeholder."
            )

    api_host = values.get("API_HOST", "")
    if (
        not re.fullmatch(
            r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"[A-Za-z]{2,63}",
            api_host,
        )
        or "example" in api_host.lower()
    ):
        errors.append(
            "API_HOST must be a real DNS hostname without a scheme or port."
        )

    public_url = urllib.parse.urlparse(values.get("PUBLIC_URL", ""))
    if public_url.scheme != "https" or not public_url.hostname:
        errors.append(
            "PUBLIC_URL must be an HTTPS URL for the hosted frontend."
        )
    elif "example" in public_url.hostname.lower():
        errors.append("PUBLIC_URL still uses an example hostname.")

    origins = [
        item.strip() for item in values.get("CORS_ORIGINS", "").split(",")
    ]
    if not origins or any(not item for item in origins):
        errors.append(
            "CORS_ORIGINS must be a comma-separated list of HTTPS origins."
        )
    else:
        for origin in origins:
            parsed_origin = urllib.parse.urlparse(origin)
            if (
                parsed_origin.scheme != "https"
                or not parsed_origin.hostname
                or parsed_origin.path not in {"", "/"}
                or parsed_origin.query
                or parsed_origin.fragment
                or "example" in parsed_origin.hostname.lower()
            ):
                errors.append(
                    "Each CORS_ORIGINS entry must be a real HTTPS origin "
                    "without a path, query or fragment."
                )
                break

    email = values.get("ACME_EMAIL", "")
    if "@" not in email or "example" in email.lower():
        errors.append(
            "ACME_EMAIL must be a real address used for certificate notices."
        )

    for key in ("SMTP_USER", "SMTP_PASSWORD"):
        value = values.get(key, "").lower()
        if value in {"change_me", "change-me", "password"} or (
            "replace-with" in value
        ):
            errors.append(f"{key} still contains a placeholder.")

    smtp_host = values.get("SMTP_HOST", "").lower()
    if not smtp_host or smtp_host == "mailpit" or "example" in smtp_host:
        errors.append("SMTP_HOST must identify a real email provider.")
    if values.get("SMTP_PORT", "") not in {"25", "465", "587", "2525"}:
        errors.append(
            "SMTP_PORT must be one of the expected SMTP ports: "
            "25, 465, 587 or 2525."
        )
    mail_from = values.get("MAIL_FROM", "")
    if "example" in mail_from.lower() or "@" not in mail_from:
        errors.append(
            "MAIL_FROM must use a sender address configured with the provider."
        )

    if values.get("ENVIRONMENT", "production").lower() != "production":
        errors.append("ENVIRONMENT must be production for this overlay.")
    seed_demo_data = values.get("SEED_DEMO_DATA", "false").lower()
    if seed_demo_data not in {"false", "0", "no"}:
        errors.append("SEED_DEMO_DATA must be false for production.")

    return errors


def main() -> int:
    """Runs environment validation and returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "env_file", type=pathlib.Path, help="Production KEY=VALUE file"
    )
    args = parser.parse_args()

    try:
        values = read_env_file(args.env_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    errors = validate(values)
    if errors:
        print("Production environment check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Production environment check passed: {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
