"""Opening, cancelling and querying shipments."""

import datetime

from halyard_common import auth
from halyard_common import db
from halyard_common import events
from operations import models
from operations import schemas
from operations.domain import shipping
from operations.services import base


class ShipmentService(base.OperationsService):
    """Opening, cancelling and querying shipments."""

    async def open_for_booking(
        self, booking: events.BookingConfirmed
    ) -> models.Shipment | None:
        """Opens the shipment of a confirmed booking.

        Creates containers, the milestone plan and the required documents,
        and marks the ``BOOKED`` milestone as reached. Does not commit; the
        event consumer owns the transaction.

        Args:
            booking: The confirmed booking.

        Returns:
            The new shipment, or None if one already exists.
        """
        if await self.shipments.get_by_booking(booking.booking_id):
            return None
        pol_name = booking.pol_name or booking.pol
        pod_name = booking.pod_name or booking.pod
        via_name = booking.via_name or booking.via
        shipment = models.Shipment(
            id=db.new_id(),
            ref=booking.booking_ref,
            booking_id=booking.booking_id,
            company_id=booking.company_id,
            contact_email=booking.contact_email,
            pol=booking.pol,
            pod=booking.pod,
            via=booking.via,
            pol_name=pol_name,
            pod_name=pod_name,
            via_name=via_name,
            carrier=booking.carrier,
            vessel=booking.vessel,
            voyage=booking.voyage,
            etd=booking.etd,
            eta=booking.eta,
            planned_eta=booking.eta,
            container_type=booking.container_type,
            commodity=booking.commodity,
            incoterm=booking.incoterm,
            gross_weight_kg=booking.gross_weight_kg,
        )
        numbers = shipping.container_numbers(
            booking.carrier, booking.booking_id, booking.quantity
        )
        shipment.containers = [
            models.Container(number=n, type=booking.container_type)
            for n in numbers
        ]
        plan = shipping.milestone_plan(
            carrier=booking.carrier,
            vessel=booking.vessel,
            pol_name=pol_name,
            pod_name=pod_name,
            via_name=via_name,
            etd=booking.etd,
            eta=booking.eta,
        )
        now = self._now()
        shipment.milestones = [
            models.Milestone(
                seq=seq,
                code=code,
                label=label,
                planned_at=planned,
                actual_at=(
                    min(now, shipping.at_nine_utc(planned))
                    if code == "BOOKED"
                    else None
                ),
            )
            for seq, (code, label, planned) in enumerate(plan)
        ]
        required = shipping.required_documents(
            booking.etd, booking.container_type
        )
        shipment.documents = [
            models.Document(
                company_id=booking.company_id,
                doc_type=doc_type,
                label=label,
                status=status,
                due_date=due,
                sort=sort,
            )
            for sort, (doc_type, label, status, due) in enumerate(required)
        ]
        await self.shipments.add(shipment)
        self.outbox.add(
            events.EventType.SHIPMENT_CREATED,
            events.ShipmentCreated(
                shipment_id=shipment.id,
                shipment_ref=shipment.ref,
                booking_id=booking.booking_id,
                company_id=booking.company_id,
                containers=numbers,
            ),
        )
        return shipment

    async def cancel_for_booking(self, booking_id: str) -> None:
        """Cancels a booking's shipment if it has not started moving.

        Does not commit; the event consumer owns the transaction.

        Args:
            booking_id: The cancelled booking.
        """
        shipment = await self.shipments.get_by_booking(booking_id)
        if shipment and shipment.status == "booked":
            shipment.status = "cancelled"

    async def list_shipments(
        self,
        user: auth.CurrentUser,
        status: str | None = None,
        query: str | None = None,
        needs_action: bool | None = None,
    ) -> list[schemas.ShipmentSummary]:
        """Lists shipments the caller may see, earliest arrival first.

        Args:
            user: The caller.
            status: A status, or ``active`` for everything not closed.
            query: Free text matched against references, vessel, ports,
                bill of lading and container numbers.
            needs_action: Only shipments that do (or do not) need action.

        Returns:
            Shipment summaries.
        """
        if status == "active":
            rows = await self.shipments.list_by_eta(
                base.company_scope(user),
                exclude_statuses=models.CLOSED_STATUSES,
            )
        else:
            rows = await self.shipments.list_by_eta(
                base.company_scope(user), status=status
            )
        if query:
            rows = [s for s in rows if _matches(s, query)]
        summaries = [schemas.ShipmentSummary.from_model(s) for s in rows]
        if needs_action is not None:
            summaries = [s for s in summaries if s.needs_action == needs_action]
        return summaries

    async def stats(self, user: auth.CurrentUser) -> schemas.ShipmentStats:
        """Computes headline numbers over the shipments the caller may see.

        Args:
            user: The caller.

        Returns:
            The numbers.
        """
        rows = await self.shipments.list_by_eta(base.company_scope(user))
        active = [s for s in rows if not s.is_closed]
        soon = self._now().date() + datetime.timedelta(days=7)
        summaries = [schemas.ShipmentSummary.from_model(s) for s in rows]
        return schemas.ShipmentStats(
            active=len(active),
            active_teu=sum(
                shipping.TEU_PER_CONTAINER.get(s.container_type, 2)
                * len(s.containers)
                for s in active
            ),
            needs_action=sum(1 for s in summaries if s.needs_action),
            arriving_7_days=sum(
                1 for s in active if s.status == "in_transit" and s.eta <= soon
            ),
            delayed=sum(1 for s in active if s.eta > s.planned_eta),
            delivered=sum(1 for s in rows if s.status == "delivered"),
            documents_to_check=sum(
                1 for s in rows for d in s.documents if d.status == "uploaded"
            ),
        )


def _matches(shipment: models.Shipment, query: str) -> bool:
    """Checks whether a shipment matches a free-text search."""
    needle = query.lower().replace(" ", "")
    haystack = " ".join(
        [
            shipment.ref,
            shipment.commodity,
            shipment.vessel,
            shipment.pol,
            shipment.pod,
            shipment.pol_name,
            shipment.pod_name,
            shipment.bill_of_lading or "",
        ]
    )
    return needle in haystack.lower().replace(" ", "") or any(
        needle in c.number.lower() for c in shipment.containers
    )
