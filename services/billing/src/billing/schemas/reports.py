"""API request and response models: reports."""

import pydantic


class MarginTotals(pydantic.BaseModel):
    """Totals across all non-void invoices."""

    shipments: int
    teu: int
    revenue_cents: int
    gross_profit_cents: int
    gross_margin_pct: float
    gross_profit_per_teu_cents: int
    open_receivables_cents: int
    overdue_cents: int


class MarginByCharge(pydantic.BaseModel):
    """Revenue and gross profit per charge code."""

    code: str
    label: str
    revenue_cents: int
    gross_profit_cents: int


class MarginShipment(pydantic.BaseModel):
    """Revenue and gross profit of one shipment."""

    shipment_ref: str
    route: str
    teu: int
    status: str
    revenue_cents: int
    cost_cents: int
    gross_profit_cents: int
    gross_profit_per_teu_cents: int


class MarginReport(pydantic.BaseModel):
    """Gross profit per shipment, per charge and per TEU."""

    totals: MarginTotals
    by_charge: list[MarginByCharge]
    shipments: list[MarginShipment]
