"""Event contracts shared by all services.

Every message on the bus is an ``EventEnvelope``. Its ``type`` doubles as the
RabbitMQ routing key. The payload models below are the contract between
services: change them carefully and only additively.
"""

import datetime
from typing import Any

import pydantic

from halyard_common import db


class EventEnvelope(pydantic.BaseModel):
    """Wrapper around every event payload.

    Attributes:
        id: Unique event id, used for idempotent consumption.
        type: Event type and routing key, see ``EventType``.
        source: Name of the publishing service.
        occurred_at: When the event was staged.
        version: Schema version of the payload.
        data: The JSON payload.
        correlation_id: Id of the request that caused the event, for tracing
            it across services in the logs. Optional, so older events stay
            valid.
    """

    id: str = pydantic.Field(default_factory=db.new_id)
    type: str
    source: str
    occurred_at: datetime.datetime = pydantic.Field(default_factory=db.utcnow)
    version: int = 1
    data: dict[str, Any]
    correlation_id: str | None = None


class EventType:
    """Event type names, which are also the routing keys."""

    USER_CREATED = "accounts.user_created"
    COMPANY_REGISTERED = "accounts.company_registered"

    BOOKING_REQUESTED = "commercial.booking_requested"
    BOOKING_CONFIRMED = "commercial.booking_confirmed"
    BOOKING_CANCELLED = "commercial.booking_cancelled"

    SHIPMENT_CREATED = "operations.shipment_created"
    MILESTONE_REACHED = "operations.milestone_reached"
    SHIPMENT_DELAYED = "operations.shipment_delayed"
    CUSTOMS_HOLD = "operations.customs_hold"
    DOCUMENT_UPLOADED = "operations.document_uploaded"
    DOCUMENT_REVIEWED = "operations.document_reviewed"
    SHIPMENT_DELIVERED = "operations.shipment_delivered"

    INVOICE_ISSUED = "billing.invoice_issued"
    INVOICE_PAID = "billing.invoice_paid"


class UserCreated(pydantic.BaseModel):
    """A user account was created (sign-up, invitation or seed)."""

    user_id: str
    company_id: str
    company_name: str
    email: str
    name: str
    role: str


class CompanyRegistered(pydantic.BaseModel):
    """A new customer company signed up."""

    company_id: str
    name: str
    customer_number: str


class PriceLine(pydantic.BaseModel):
    """One charge on a booking, with our sell price and our cost."""

    code: str
    label: str
    quantity: int = 1
    sell_cents: int
    cost_cents: int


class BookingRequested(pydantic.BaseModel):
    """A customer booked a quote option; ops must confirm it."""

    booking_id: str
    booking_ref: str
    company_id: str
    requested_by_email: str
    pol: str
    pod: str
    carrier: str
    container_type: str
    quantity: int
    etd: datetime.date
    total_sell_cents: int


class BookingConfirmed(pydantic.BaseModel):
    """Ops confirmed space with the carrier."""

    booking_id: str
    booking_ref: str
    company_id: str
    contact_email: str
    pol: str
    pod: str
    via: str | None = None
    pol_name: str | None = None
    pod_name: str | None = None
    via_name: str | None = None
    carrier: str
    vessel: str
    voyage: str
    etd: datetime.date
    eta: datetime.date
    container_type: str
    quantity: int
    commodity: str
    incoterm: str
    gross_weight_kg: int
    cargo_value_cents: int
    currency: str = "EUR"
    lines: list[PriceLine]


class BookingCancelled(pydantic.BaseModel):
    """A booking was cancelled by the customer or ops."""

    booking_id: str
    booking_ref: str
    company_id: str
    reason: str | None = None


class ShipmentCreated(pydantic.BaseModel):
    """Operations opened a shipment for a confirmed booking."""

    shipment_id: str
    shipment_ref: str
    booking_id: str
    company_id: str
    containers: list[str]


class MilestoneReached(pydantic.BaseModel):
    """A shipment reached a milestone such as DEPARTED or ARRIVED."""

    shipment_id: str
    shipment_ref: str
    booking_id: str
    company_id: str
    code: str
    label: str
    at: datetime.datetime
    location: str | None = None


class ShipmentDelayed(pydantic.BaseModel):
    """A shipment's arrival moved later."""

    shipment_id: str
    shipment_ref: str
    company_id: str
    previous_eta: datetime.date
    new_eta: datetime.date
    reason: str | None = None


class CustomsHold(pydantic.BaseModel):
    """Customs is holding a shipment."""

    shipment_id: str
    shipment_ref: str
    company_id: str
    reason: str


class DocumentUploaded(pydantic.BaseModel):
    """A shipment document was uploaded by a customer or ops."""

    document_id: str
    shipment_id: str
    shipment_ref: str
    company_id: str
    doc_type: str
    label: str
    uploaded_by_email: str


class DocumentReviewed(pydantic.BaseModel):
    """A shipment document was approved or sent back."""

    document_id: str
    shipment_id: str
    shipment_ref: str
    company_id: str
    label: str
    approved: bool
    note: str | None = None
    reviewed_by_email: str | None = None


class ShipmentDelivered(pydantic.BaseModel):
    """Every container of a shipment was delivered."""

    shipment_id: str
    shipment_ref: str
    booking_id: str
    company_id: str
    delivered_at: datetime.datetime


class InvoiceIssued(pydantic.BaseModel):
    """An invoice was issued to the customer."""

    invoice_id: str
    number: str
    company_id: str
    shipment_ref: str
    total_cents: int
    currency: str
    due_date: datetime.date


class InvoicePaid(pydantic.BaseModel):
    """An invoice was marked as paid."""

    invoice_id: str
    number: str
    company_id: str
    total_cents: int


PAYLOADS: dict[str, type[pydantic.BaseModel]] = {
    EventType.USER_CREATED: UserCreated,
    EventType.COMPANY_REGISTERED: CompanyRegistered,
    EventType.BOOKING_REQUESTED: BookingRequested,
    EventType.BOOKING_CONFIRMED: BookingConfirmed,
    EventType.BOOKING_CANCELLED: BookingCancelled,
    EventType.SHIPMENT_CREATED: ShipmentCreated,
    EventType.MILESTONE_REACHED: MilestoneReached,
    EventType.SHIPMENT_DELAYED: ShipmentDelayed,
    EventType.CUSTOMS_HOLD: CustomsHold,
    EventType.DOCUMENT_UPLOADED: DocumentUploaded,
    EventType.DOCUMENT_REVIEWED: DocumentReviewed,
    EventType.SHIPMENT_DELIVERED: ShipmentDelivered,
    EventType.INVOICE_ISSUED: InvoiceIssued,
    EventType.INVOICE_PAID: InvoicePaid,
}


def parse_payload(envelope: EventEnvelope) -> pydantic.BaseModel:
    """Validates an envelope's data against its registered payload model.

    Args:
        envelope: The received event.

    Returns:
        The typed payload.

    Raises:
        KeyError: The event type is unknown.
        pydantic.ValidationError: The data does not match the contract.
    """
    return PAYLOADS[envelope.type].model_validate(envelope.data)
