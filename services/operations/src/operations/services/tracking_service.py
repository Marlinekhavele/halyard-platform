"""Applying tracking events from the provider or the simulator."""

import dataclasses
import datetime
import hmac

from halyard_common import auth
from halyard_common import errors
from halyard_common import events
from operations import models
from operations import schemas
from operations.domain import shipping
from operations.services import base


@dataclasses.dataclass(frozen=True)
class TrackingOutcome:
    """What a tracking event changed.

    Attributes:
        shipment: The affected shipment.
        applied: Human-readable description of the effect.
    """

    shipment: models.Shipment
    applied: str


class TrackingService(base.OperationsService):
    """Applies tracking events from the provider or the simulator."""

    async def receive_webhook(
        self, token: str | None, update: schemas.TrackingWebhook
    ) -> TrackingOutcome:
        """Handles one event from the tracking provider.

        Args:
            token: The ``X-Tracking-Token`` header.
            update: The normalised event.

        Returns:
            What changed.

        Raises:
            errors.AuthenticationError: The token is wrong.
            errors.NotFoundError: The container is unknown.
            errors.InvalidRequestError: The event is invalid.
        """
        # Constant-time comparison, so response timing reveals nothing about
        # how much of the shared secret a caller guessed.
        expected = self._settings.tracking_webhook_token.encode()
        if not hmac.compare_digest((token or "").encode(), expected):
            raise errors.AuthenticationError("Invalid tracking token.")
        number = update.container_number.replace(" ", "").upper()
        container = await self.containers.get_by_number(number)
        if not container:
            raise errors.NotFoundError(f"Unknown container {number}.")
        shipment = await self.shipments.get(container.shipment_id)
        applied = self.apply(shipment, container, update)
        await self._session.commit()
        return TrackingOutcome(shipment=shipment, applied=applied)

    async def simulate(
        self, user: auth.CurrentUser, key: str, step: schemas.SimulateStep
    ) -> models.Shipment:
        """Moves a shipment on as if every container reported an event.

        Demo and testing helper. Ops only.

        Args:
            user: The caller.
            key: Shipment id or reference.
            step: The event; empty means the next milestone.

        Returns:
            The updated shipment.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
            errors.NotFoundError: The shipment does not exist.
            errors.ConflictError: Every milestone is already reached.
            errors.InvalidRequestError: The event is invalid.
        """
        auth.require_ops(user)
        shipment = await self.get_visible_shipment(user, key)
        event = step.event
        if not event:
            upcoming = next(
                (m for m in shipment.milestones if not m.actual_at), None
            )
            if not upcoming:
                raise errors.ConflictError(
                    "This shipment has reached every milestone."
                )
            event = upcoming.code
        at = step.occurred_at or self._now()
        for container in shipment.containers:
            self.apply(
                shipment,
                container,
                schemas.TrackingWebhook(
                    container_number=container.number,
                    event=event,
                    occurred_at=at,
                    new_eta=step.new_eta,
                    reason=step.reason,
                    location=_simulated_location(shipment, event),
                ),
            )
        await self._session.commit()
        await self._session.refresh(shipment)
        return shipment

    def apply(
        self,
        shipment: models.Shipment,
        container: models.Container,
        update: schemas.TrackingWebhook,
    ) -> str:
        """Applies one container event to its shipment. Does not commit.

        Missing earlier milestones are filled in, because providers
        sometimes skip events. ``DELIVERED`` is only recorded once every
        container has been delivered.

        Args:
            shipment: The container's shipment.
            container: The container that reported the event.
            update: The event.

        Returns:
            Human-readable description of the effect.

        Raises:
            errors.InvalidRequestError: Unknown event, or ``ETA_CHANGED``
                without a new ETA.
        """
        event = update.event.upper()
        if event not in shipping.TRACKING_EVENTS:
            raise errors.InvalidRequestError(f"Unknown tracking event {event}.")
        if event == "ETA_CHANGED" and not update.new_eta:
            raise errors.InvalidRequestError("ETA_CHANGED needs new_eta.")
        if shipment.is_closed:
            return f"ignored: shipment is {shipment.status}"
        at = update.occurred_at
        if not at.tzinfo:
            at = at.replace(tzinfo=datetime.UTC)

        self.tracking_events.record(
            models.TrackingEvent(
                shipment_id=shipment.id,
                container_number=container.number,
                event=event,
                occurred_at=at,
                location=update.location,
                description=update.description,
                raw=update.model_dump(mode="json"),
            )
        )
        container.last_event = event
        container.last_event_at = at
        container.last_location = update.location

        if event == "ETA_CHANGED":
            return self._change_eta(shipment, update)
        if event == "CUSTOMS_HOLD":
            return self._hold(shipment, update)
        return self._reach_milestone(shipment, event, at, update.location)

    def _change_eta(
        self, shipment: models.Shipment, update: schemas.TrackingWebhook
    ) -> str:
        assert update.new_eta is not None
        shift = (update.new_eta - shipment.eta).days
        if shift == 0:
            return "no change"
        previous = shipment.eta
        shipment.eta = update.new_eta
        arrived_seq = next(
            (m.seq for m in shipment.milestones if m.code == "ARRIVED"), 0
        )
        for milestone in shipment.milestones:
            if milestone.seq >= arrived_seq and not milestone.actual_at:
                milestone.planned_at += datetime.timedelta(days=shift)
        if shift > 0:
            shipment.delay_reason = update.reason or update.description
            self.outbox.add(
                events.EventType.SHIPMENT_DELAYED,
                events.ShipmentDelayed(
                    shipment_id=shipment.id,
                    shipment_ref=shipment.ref,
                    company_id=shipment.company_id,
                    previous_eta=previous,
                    new_eta=update.new_eta,
                    reason=shipment.delay_reason,
                ),
            )
        return f"eta moved {shift:+d} days"

    def _hold(
        self, shipment: models.Shipment, update: schemas.TrackingWebhook
    ) -> str:
        shipment.status = "customs_hold"
        shipment.hold_reason = (
            update.reason
            or update.description
            or "Held by customs for inspection."
        )
        self.outbox.add(
            events.EventType.CUSTOMS_HOLD,
            events.CustomsHold(
                shipment_id=shipment.id,
                shipment_ref=shipment.ref,
                company_id=shipment.company_id,
                reason=shipment.hold_reason,
            ),
        )
        return "customs hold"

    def _reach_milestone(
        self,
        shipment: models.Shipment,
        event: str,
        at: datetime.datetime,
        location: str | None,
    ) -> str:
        milestone = next(
            (m for m in shipment.milestones if m.code == event), None
        )
        if milestone is None:
            return f"ignored: no {event} milestone on this route"
        if milestone.actual_at:
            return "already recorded"
        if event == "DELIVERED" and any(
            c.last_event != "DELIVERED" for c in shipment.containers
        ):
            return "container delivered; waiting for the others"

        # Earlier steps must have happened even if the provider skipped them.
        for earlier in shipment.milestones:
            if earlier.seq < milestone.seq and not earlier.actual_at:
                earlier.actual_at = min(
                    at, shipping.at_nine_utc(earlier.planned_at)
                )
        milestone.actual_at = at
        milestone.location = location
        shipment.status = shipping.STATUS_AFTER.get(event, shipment.status)
        if event == "CUSTOMS_RELEASED":
            shipment.hold_reason = None
        if event == "DEPARTED" and not shipment.bill_of_lading:
            shipment.bill_of_lading = shipping.bill_of_lading_number(
                shipment.carrier, shipment.ref, at
            )
        if event == "ARRIVED":
            shipment.eta = at.date()
        self.outbox.add(
            events.EventType.MILESTONE_REACHED,
            events.MilestoneReached(
                shipment_id=shipment.id,
                shipment_ref=shipment.ref,
                booking_id=shipment.booking_id,
                company_id=shipment.company_id,
                code=milestone.code,
                label=milestone.label,
                at=at,
                location=location,
            ),
        )
        if event == "DELIVERED":
            shipment.delivered_at = at
            self.outbox.add(
                events.EventType.SHIPMENT_DELIVERED,
                events.ShipmentDelivered(
                    shipment_id=shipment.id,
                    shipment_ref=shipment.ref,
                    booking_id=shipment.booking_id,
                    company_id=shipment.company_id,
                    delivered_at=at,
                ),
            )
        return f"{event.lower()} recorded"


def _simulated_location(shipment: models.Shipment, event: str) -> str | None:
    """Picks a plausible location for a simulated event."""
    if event in shipping.ORIGIN_EVENTS:
        return shipment.pol_name
    if event == "TRANSSHIPMENT":
        return shipment.via_name
    return shipment.pod_name
