"""FastAPI dependencies that build the use-case classes per request."""

from typing import Annotated

import fastapi

from billing import services
from billing.core import config
from halyard_common import dependencies


def get_invoice_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.InvoiceService:
    """Builds the invoice service for one request."""
    settings = dependencies.get_settings(request)
    assert isinstance(settings, config.Settings)
    return services.InvoiceService(session, settings)


Invoices = Annotated[
    services.InvoiceService, fastapi.Depends(get_invoice_service)
]
