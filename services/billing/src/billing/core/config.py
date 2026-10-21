"""Settings of the Billing service."""

import pydantic

from halyard_common import config


class Settings(config.ServiceSettings):
    """Billing settings.

    Attributes:
        database_url: Read from ``BILLING_DATABASE_URL`` or ``DATABASE_URL``.
        payment_terms_days: Days between issue date and due date.
        vat_rate_bp: VAT rate in basis points. International sea freight is
            often VAT-exempt in Germany (§ 4 Nr. 3 UStG); confirm the
            treatment for each service with a tax adviser.
    """

    service_name: str = "billing"
    database_url: str = pydantic.Field(
        "sqlite+aiosqlite:///./billing.db",
        validation_alias=pydantic.AliasChoices(
            "BILLING_DATABASE_URL", "DATABASE_URL"
        ),
    )
    payment_terms_days: int = 14
    vat_rate_bp: int = 0
