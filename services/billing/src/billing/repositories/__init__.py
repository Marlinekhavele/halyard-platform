"""Repositories of the billing service, one module per entity."""

from billing.repositories.invoice_repository import InvoiceRepository

__all__ = [
    "InvoiceRepository",
]
