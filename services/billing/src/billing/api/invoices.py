"""HTTP routes: invoices."""

import fastapi

from billing import schemas
from billing.api import deps
from halyard_common import dependencies

router = fastapi.APIRouter()


@router.get(
    "/invoices", response_model=list[schemas.InvoiceOut], tags=["invoices"]
)
async def list_invoices(
    user: dependencies.CurrentUser,
    invoices: deps.Invoices,
    status_filter: str | None = fastapi.Query(None, alias="status"),
) -> list[schemas.InvoiceOut]:
    """Lists invoices; customers only see issued and later ones."""
    today = invoices.today()
    return [
        schemas.InvoiceOut.from_model(inv, user.is_ops, today)
        for inv in await invoices.list_invoices(user, status_filter)
    ]


@router.get(
    "/invoices/{invoice_id}",
    response_model=schemas.InvoiceOut,
    tags=["invoices"],
)
async def get_invoice(
    invoice_id: str, user: dependencies.CurrentUser, invoices: deps.Invoices
) -> schemas.InvoiceOut:
    """Returns one invoice."""
    invoice = await invoices.get_invoice(user, invoice_id)
    return schemas.InvoiceOut.from_model(invoice, user.is_ops, invoices.today())


@router.post(
    "/invoices/{invoice_id}/mark-paid",
    response_model=schemas.InvoiceOut,
    tags=["invoices"],
)
async def mark_paid(
    invoice_id: str, user: dependencies.OpsUser, invoices: deps.Invoices
) -> schemas.InvoiceOut:
    """Records payment of an issued invoice."""
    invoice = await invoices.mark_paid(user, invoice_id)
    return schemas.InvoiceOut.from_model(invoice, user.is_ops, invoices.today())
