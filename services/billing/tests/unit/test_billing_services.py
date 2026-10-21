"""Tests for billing.services and its repository."""

import datetime

import pytest
import sqlalchemy as sa

from billing import models
from halyard_common import errors
from halyard_common import events
from halyard_common import testing

from .. import conftest

CUSTOMER = testing.customer_user()
OTHER_CUSTOMER = testing.customer_user(testing.OTHER_COMPANY_ID)
OPS = testing.ops_user()


async def _staged_types(session) -> list[str]:
    return list(await session.scalars(sa.select(models.OutboxEvent.type)))


async def _issued(service, booking_id: str = "booking-1") -> models.Invoice:
    await service.draft_for_booking(conftest.booking_confirmed(booking_id))
    return await service.issue_on_departure(conftest.departed(booking_id))


async def test_draft_totals_and_teu(service):
    invoice = await service.draft_for_booking(conftest.booking_confirmed())

    assert invoice.status == "draft"
    assert invoice.number is None
    assert invoice.subtotal_cents == 100_000
    assert invoice.vat_cents == 0
    assert invoice.total_cents == 100_000
    assert invoice.cost_cents == 80_000
    assert invoice.gross_profit_cents == 20_000
    assert invoice.teu == 4
    assert [line.code for line in invoice.lines] == ["OCEAN", "DOC"]


async def test_vat_is_applied_from_settings(make_service):
    service = make_service(vat_rate_bp=1900)

    invoice = await service.draft_for_booking(conftest.booking_confirmed())

    assert invoice.vat_cents == 19_000
    assert invoice.total_cents == 119_000


async def test_draft_is_created_once_per_booking(service):
    await service.draft_for_booking(conftest.booking_confirmed())

    assert await service.draft_for_booking(conftest.booking_confirmed()) is None


async def test_departure_issues_invoice(service, session):
    invoice = await _issued(service)

    assert invoice.status == "issued"
    assert invoice.number == "INV-2026-00001"
    assert invoice.issue_date == datetime.date(2026, 10, 10)
    assert invoice.due_date == datetime.date(2026, 10, 24)
    await session.flush()
    assert await _staged_types(session) == [events.EventType.INVOICE_ISSUED]


async def test_invoice_numbers_count_up(service):
    await _issued(service, "b1")

    second = await _issued(service, "b2")

    assert second.number == "INV-2026-00002"


async def test_other_milestones_do_not_issue(service):
    await service.draft_for_booking(conftest.booking_confirmed())
    arrived = conftest.departed().model_copy(update={"code": "ARRIVED"})

    assert await service.issue_on_departure(arrived) is None


async def test_cancelled_booking_voids_only_drafts(service):
    draft = await service.draft_for_booking(conftest.booking_confirmed("b1"))
    issued = await _issued(service, "b2")

    await service.void_for_booking("b1")
    await service.void_for_booking("b2")

    assert draft.status == "void"
    assert issued.status == "issued"


async def test_delivery_is_recorded(service):
    invoice = await service.draft_for_booking(conftest.booking_confirmed())
    delivered_at = datetime.datetime(2026, 11, 20, tzinfo=datetime.UTC)

    await service.record_delivery(
        events.ShipmentDelivered(
            shipment_id="s1",
            shipment_ref="HLY-booking-1",
            booking_id="booking-1",
            company_id=testing.CUSTOMER_COMPANY_ID,
            delivered_at=delivered_at,
        )
    )

    assert invoice.delivered_at == delivered_at


async def test_customers_never_see_drafts(service):
    draft = await service.draft_for_booking(conftest.booking_confirmed("b1"))
    await _issued(service, "b2")

    assert [
        i.booking_id for i in await service.list_invoices(CUSTOMER, None)
    ] == ["b2"]
    assert len(await service.list_invoices(OPS, None)) == 2
    with pytest.raises(errors.NotFoundError):
        await service.get_invoice(CUSTOMER, draft.id)
    assert await service.get_invoice(OPS, draft.id)


async def test_other_companies_cannot_see_invoices(service):
    invoice = await _issued(service)

    assert await service.list_invoices(OTHER_CUSTOMER, None) == []
    with pytest.raises(errors.NotFoundError):
        await service.get_invoice(OTHER_CUSTOMER, invoice.id)


async def test_mark_paid(service, session):
    draft = await service.draft_for_booking(conftest.booking_confirmed())
    await session.commit()

    with pytest.raises(errors.ConflictError, match="draft"):
        await service.mark_paid(OPS, draft.id)
    await service.issue_on_departure(conftest.departed())
    with pytest.raises(errors.PermissionDeniedError):
        await service.mark_paid(CUSTOMER, draft.id)

    paid = await service.mark_paid(OPS, draft.id)

    assert paid.status == "paid"
    assert paid.paid_at is not None
    assert events.EventType.INVOICE_PAID in await _staged_types(session)


async def test_overdue(service):
    invoice = await _issued(service)

    assert not invoice.is_overdue(invoice.due_date)
    assert invoice.is_overdue(invoice.due_date + datetime.timedelta(days=1))


async def test_margin_report(make_service):
    service = make_service(today=conftest.TODAY + datetime.timedelta(days=30))
    await _issued(service, "b1")
    await service.draft_for_booking(conftest.booking_confirmed("b2"))
    await service.draft_for_booking(conftest.booking_confirmed("b3"))
    await service.void_for_booking("b3")

    report = await service.margin_report(OPS)

    totals = report.totals
    assert totals.shipments == 2  # The void invoice is excluded.
    assert totals.teu == 8
    assert totals.revenue_cents == 200_000
    assert totals.gross_profit_cents == 40_000
    assert totals.gross_margin_pct == 20.0
    assert totals.gross_profit_per_teu_cents == 5_000
    assert totals.open_receivables_cents == 100_000
    assert totals.overdue_cents == 100_000
    by_charge = {b.code: b for b in report.by_charge}
    assert by_charge["OCEAN"].label == "Ocean freight"
    assert by_charge["DOC"].gross_profit_cents == 20_000
    profits = [b.gross_profit_cents for b in report.by_charge]
    assert profits == sorted(profits, reverse=True)  # Most profitable first.


async def test_margin_report_is_ops_only_and_handles_no_data(service):
    empty = await service.margin_report(OPS)

    assert empty.totals.gross_margin_pct == 0
    with pytest.raises(errors.PermissionDeniedError):
        await service.margin_report(CUSTOMER)
