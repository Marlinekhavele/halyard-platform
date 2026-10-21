"""Tests for the Notifications handlers, service and API."""

import datetime

import pytest
import sqlalchemy as sa

from halyard_common import bus
from halyard_common import events
from halyard_common import testing
from notifications import models
from notifications import services
from notifications.core import mailer
from notifications.events import handlers

from .. import conftest

COMPANY = testing.CUSTOMER_COMPANY_ID
UTC = datetime.UTC


async def _notifications(session) -> list[models.Notification]:
    rows = await session.scalars(
        sa.select(models.Notification).order_by(models.Notification.created_at)
    )
    return list(rows)


def _document_uploaded(by: str) -> events.DocumentUploaded:
    return events.DocumentUploaded(
        document_id="d1",
        shipment_id="s1",
        shipment_ref="HLY-1",
        company_id=COMPANY,
        doc_type="PACKING_LIST",
        label="Packing list",
        uploaded_by_email=by,
    )


def _document_reviewed(by: str, approved: bool) -> events.DocumentReviewed:
    return events.DocumentReviewed(
        document_id="d1",
        shipment_id="s1",
        shipment_ref="HLY-1",
        company_id=COMPANY,
        label="Packing list",
        approved=approved,
        note=None if approved else "Wrong weights",
        reviewed_by_email=by,
    )


# ---- Formatting ------------------------------------------------------------


def test_formatting_helpers():
    assert handlers.euros(123_456) == "€1,234.56"
    assert handlers.day(datetime.date(2026, 10, 5)) == "Mon 05 Oct 2026"
    assert handlers.plural_days(1) == "1 day"
    assert handlers.plural_days(3) == "3 days"


# ---- Recipients ------------------------------------------------------------


async def test_new_customers_are_welcomed_but_ops_are_not(session, fake_mailer):
    event_handlers = handlers.EventHandlers(fake_mailer)

    for user in (
        conftest.user_created("u1", "a@x.example", "customer", COMPANY),
        conftest.user_created(
            "u2", "o@h.example", "ops", testing.OPS_COMPANY_ID
        ),
    ):
        await event_handlers.on_user_created(
            session, conftest.envelope(events.EventType.USER_CREATED, user)
        )

    sent = [(to, subject) for to, subject, _ in fake_mailer.sent]
    assert sent == [(["a@x.example"], services.WELCOME_SUBJECT)]


async def test_repeated_user_event_updates_recipient(session, fake_mailer):
    service = services.NotificationService(session, fake_mailer)
    await service.register_recipient(
        conftest.user_created("u1", "old@x.example", "customer", COMPANY)
    )

    await service.register_recipient(
        conftest.user_created("u1", "new@x.example", "customer_admin", COMPANY)
    )

    recipient = await service.recipients.get("u1")
    assert recipient.email == "new@x.example"
    assert recipient.role == "customer_admin"
    assert len(fake_mailer.sent) == 1


# ---- Routing events to audiences -------------------------------------------


async def test_booking_request_goes_to_ops(
    event_handlers, session, fake_mailer
):
    await event_handlers.on_booking_requested(
        session,
        conftest.envelope(
            events.EventType.BOOKING_REQUESTED,
            events.BookingRequested(
                booking_id="b1",
                booking_ref="HLY-1",
                company_id=COMPANY,
                requested_by_email=conftest.CUSTOMER_EMAIL,
                pol="CNSHA",
                pod="DEHAM",
                carrier="MSC",
                container_type="40HC",
                quantity=2,
                etd=datetime.date(2026, 10, 5),
                total_sell_cents=512_000,
            ),
        ),
    )

    [note] = await _notifications(session)
    assert note.audience == "ops"
    assert note.kind == "action"
    assert "€5,120.00" in note.body
    assert note.emailed_to == conftest.OPS_EMAIL
    assert note.email_status == "sent"


async def test_only_customer_facing_milestones_notify(event_handlers, session):
    for code in ("GATE_IN", "DEPARTED"):
        await event_handlers.on_milestone_reached(
            session,
            conftest.envelope(
                events.EventType.MILESTONE_REACHED,
                events.MilestoneReached(
                    shipment_id="s1",
                    shipment_ref="HLY-1",
                    booking_id="b1",
                    company_id=COMPANY,
                    code=code,
                    label=code.title(),
                    at=datetime.datetime(2026, 10, 5, tzinfo=UTC),
                ),
            ),
        )

    [note] = await _notifications(session)
    assert note.title == "HLY-1: Departed"
    assert note.audience == "customer"


async def test_delay_reaches_customer_and_ops(
    event_handlers, session, fake_mailer
):
    await event_handlers.on_shipment_delayed(
        session,
        conftest.envelope(
            events.EventType.SHIPMENT_DELAYED,
            events.ShipmentDelayed(
                shipment_id="s1",
                shipment_ref="HLY-1",
                company_id=COMPANY,
                previous_eta=datetime.date(2026, 11, 1),
                new_eta=datetime.date(2026, 11, 2),
                reason="Fog",
            ),
        ),
    )

    notes = await _notifications(session)
    assert [n.audience for n in notes] == ["customer", "ops"]
    assert notes[0].title == "HLY-1 is running 1 day late"
    assert notes[0].body.endswith("Fog")
    assert [to for to, _, _ in fake_mailer.sent] == [
        [conftest.CUSTOMER_EMAIL],
        [conftest.OPS_EMAIL],
    ]


@pytest.mark.parametrize(
    ("uploaded_by", "audience", "title"),
    [
        (conftest.CUSTOMER_EMAIL, "ops", "HLY-1: Packing list uploaded"),
        (
            conftest.OPS_EMAIL,
            "customer",
            "HLY-1: Packing list ready for your approval",
        ),
    ],
)
async def test_document_upload_notifies_the_other_side(
    event_handlers, session, uploaded_by, audience, title
):
    await event_handlers.on_document_uploaded(
        session,
        conftest.envelope(
            events.EventType.DOCUMENT_UPLOADED,
            _document_uploaded(uploaded_by),
        ),
    )

    [note] = await _notifications(session)
    assert (note.audience, note.title) == (audience, title)


@pytest.mark.parametrize(
    ("reviewer", "approved", "audience", "title"),
    [
        (conftest.OPS_EMAIL, True, "customer", "HLY-1: Packing list approved"),
        (
            conftest.OPS_EMAIL,
            False,
            "customer",
            "HLY-1: Packing list needs changes",
        ),
        (
            conftest.CUSTOMER_EMAIL,
            True,
            "ops",
            "HLY-1: customer approved on Packing list",
        ),
        (
            conftest.CUSTOMER_EMAIL,
            False,
            "ops",
            "HLY-1: customer requested changes on Packing list",
        ),
    ],
)
async def test_document_review_notifies_the_uploader(
    event_handlers, session, reviewer, approved, audience, title
):
    await event_handlers.on_document_reviewed(
        session,
        conftest.envelope(
            events.EventType.DOCUMENT_REVIEWED,
            _document_reviewed(reviewer, approved),
        ),
    )

    [note] = await _notifications(session)
    assert (note.audience, note.title) == (audience, title)


async def test_notification_without_recipients_is_still_stored(
    session, fake_mailer
):
    service = services.NotificationService(session, fake_mailer)

    note = await service.notify(
        "x.y",
        audience="customer",
        company_id="nobody",
        kind="info",
        title="Hello",
        body="World",
    )

    assert note.emailed_to is None
    assert note.email_status == "no recipients"


async def test_smtp_mailer_only_logs_without_host(settings):
    smtp = mailer.SmtpMailer(settings)

    assert await smtp.send(["a@x.example"], "Hi", "Text") == "logged"
    assert await smtp.send([], "Hi", "Text") == "no recipients"


# ---- API -------------------------------------------------------------------


async def _publish(event_type: str, payload) -> None:
    await bus.InMemoryBus().publish(conftest.envelope(event_type, payload))


async def test_feeds_are_separated_and_can_be_marked_read(client, settings):
    await _publish(
        events.EventType.USER_CREATED,
        conftest.user_created(
            "u2", conftest.OPS_EMAIL, "ops", testing.OPS_COMPANY_ID
        ),
    )
    await _publish(
        events.EventType.DOCUMENT_UPLOADED,
        _document_uploaded(conftest.CUSTOMER_EMAIL),
    )
    await _publish(
        events.EventType.DOCUMENT_UPLOADED,
        _document_uploaded(conftest.OPS_EMAIL),
    )
    customer = testing.auth_headers(settings, testing.customer_user())
    other = testing.auth_headers(
        settings, testing.customer_user(testing.OTHER_COMPANY_ID)
    )
    ops = testing.auth_headers(settings, testing.ops_user())

    [mine] = (await client.get("/notifications", headers=customer)).json()
    [ops_note] = (await client.get("/notifications", headers=ops)).json()
    assert "approval" in mine["title"]
    assert "uploaded" in ops_note["title"]
    assert (await client.get("/notifications", headers=other)).json() == []

    r = await client.post("/notifications/read-all", headers=customer)
    assert r.json() == {"status": "ok"}
    [mine] = (await client.get("/notifications", headers=customer)).json()
    assert mine["read_at"] is not None
    [ops_note] = (await client.get("/notifications", headers=ops)).json()
    assert ops_note["read_at"] is None
    assert not bus.InMemoryBus.dead_letters


async def test_notifications_require_sign_in(client):
    assert (await client.get("/notifications")).status_code == 401
