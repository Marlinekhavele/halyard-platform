"""API request and response models: shipments."""

import datetime
from typing import Self

import pydantic

from operations import models
from operations.domain import shipping
from operations.schemas import documents


class ContainerOut(pydantic.BaseModel):
    """A container and its latest tracking event."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    number: str
    type: str
    last_event: str | None
    last_event_at: datetime.datetime | None
    last_location: str | None


class MilestoneOut(pydantic.BaseModel):
    """A planned or reached milestone."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    seq: int
    code: str
    label: str
    planned_at: datetime.date
    actual_at: datetime.datetime | None
    location: str | None


class ShipmentSummary(pydantic.BaseModel):
    """A shipment as shown in lists."""

    id: str
    ref: str
    booking_id: str
    company_id: str
    status: str
    pol: str
    pod: str
    via: str | None
    pol_name: str
    pod_name: str
    via_name: str | None
    carrier: str
    vessel: str
    voyage: str
    etd: datetime.date
    eta: datetime.date
    planned_eta: datetime.date
    delay_days: int
    container_type: str
    container_count: int
    commodity: str
    open_documents: int
    progress: float
    next_milestone: str | None
    needs_action: bool

    @staticmethod
    def fields_of(shipment: models.Shipment) -> dict:
        """Computes the summary fields of a shipment.

        Args:
            shipment: The stored shipment with its children loaded.

        Returns:
            Field values for ``ShipmentSummary`` and ``ShipmentDetail``.
        """
        milestones = shipment.milestones
        reached = sum(1 for m in milestones if m.actual_at)
        upcoming = next((m for m in milestones if not m.actual_at), None)
        open_docs = sum(
            1
            for d in shipment.documents
            if d.status in shipping.OPEN_FOR_CUSTOMER
        )
        return {
            "id": shipment.id,
            "ref": shipment.ref,
            "booking_id": shipment.booking_id,
            "company_id": shipment.company_id,
            "status": shipment.status,
            "pol": shipment.pol,
            "pod": shipment.pod,
            "via": shipment.via,
            "pol_name": shipment.pol_name,
            "pod_name": shipment.pod_name,
            "via_name": shipment.via_name,
            "carrier": shipment.carrier,
            "vessel": shipment.vessel,
            "voyage": shipment.voyage,
            "etd": shipment.etd,
            "eta": shipment.eta,
            "planned_eta": shipment.planned_eta,
            "delay_days": max(0, (shipment.eta - shipment.planned_eta).days),
            "container_type": shipment.container_type,
            "container_count": len(shipment.containers),
            "commodity": shipment.commodity,
            "open_documents": open_docs,
            "progress": (
                round(reached / len(milestones), 3) if milestones else 0
            ),
            "next_milestone": upcoming.label if upcoming else None,
            "needs_action": open_docs > 0 or shipment.status == "customs_hold",
        }

    @classmethod
    def from_model(cls, shipment: models.Shipment) -> Self:
        """Builds the summary of a stored shipment.

        Args:
            shipment: The stored shipment.

        Returns:
            The response model.
        """
        return cls(**cls.fields_of(shipment))


class ShipmentDetail(ShipmentSummary):
    """A shipment with containers, milestones and documents."""

    contact_email: str
    incoterm: str
    gross_weight_kg: int
    bill_of_lading: str | None
    delay_reason: str | None
    hold_reason: str | None
    delivered_at: datetime.datetime | None
    containers: list[ContainerOut]
    milestones: list[MilestoneOut]
    documents: list[documents.DocumentOut]

    @classmethod
    def from_model(cls, shipment: models.Shipment) -> Self:
        """Builds the detail view of a stored shipment.

        Args:
            shipment: The stored shipment.

        Returns:
            The response model.
        """
        return cls(
            **cls.fields_of(shipment),
            contact_email=shipment.contact_email,
            incoterm=shipment.incoterm,
            gross_weight_kg=shipment.gross_weight_kg,
            bill_of_lading=shipment.bill_of_lading,
            delay_reason=shipment.delay_reason,
            hold_reason=shipment.hold_reason,
            delivered_at=shipment.delivered_at,
            containers=[
                ContainerOut.model_validate(c) for c in shipment.containers
            ],
            milestones=[
                MilestoneOut.model_validate(m) for m in shipment.milestones
            ],
            documents=[
                documents.DocumentOut.from_model(d, shipment.ref)
                for d in shipment.documents
            ],
        )


class ShipmentStats(pydantic.BaseModel):
    """Headline numbers for the dashboard."""

    active: int
    active_teu: int
    needs_action: int
    arriving_7_days: int
    delayed: int
    delivered: int
    documents_to_check: int
