"""Booking lifecycle: list, confirm with the carrier, cancel."""

from collections.abc import Sequence

from commercial import models
from commercial import schemas
from commercial.services import base
from halyard_common import auth
from halyard_common import db
from halyard_common import errors
from halyard_common import events


class BookingService(base.CommercialService):
    """Booking lifecycle: list, confirm with the carrier, cancel."""

    async def list_bookings(
        self, user: auth.CurrentUser, status: str | None
    ) -> Sequence[models.Booking]:
        """Returns bookings the caller may see.

        Args:
            user: The caller.
            status: Only bookings in this status.

        Returns:
            The bookings, newest first.
        """
        return await self.bookings.list_recent(base.company_scope(user), status)

    async def get_booking(
        self, user: auth.CurrentUser, booking_id: str
    ) -> models.Booking:
        """Returns a booking the caller may see.

        Args:
            user: The caller.
            booking_id: The booking.

        Returns:
            The booking.

        Raises:
            errors.NotFoundError: The booking does not exist or is not
                visible.
        """
        booking = await self.bookings.get(booking_id)
        if not booking or not user.can_see_company(booking.company_id):
            raise errors.NotFoundError("Booking not found.")
        return booking

    async def confirm(
        self,
        user: auth.CurrentUser,
        booking_id: str,
        confirmation: schemas.ConfirmBooking,
    ) -> models.Booking:
        """Confirms carrier space for a requested booking. Ops only.

        Operations then opens the shipment and Billing drafts the invoice.
        A changed departure shifts the arrival by the same number of days
        unless an arrival is given too.

        Args:
            user: The caller.
            booking_id: The booking.
            confirmation: Vessel, voyage and optional new schedule.

        Returns:
            The confirmed booking.

        Raises:
            errors.PermissionDeniedError: The caller is not ops.
            errors.NotFoundError: The booking does not exist.
            errors.ConflictError: The booking is not in ``requested``.
        """
        auth.require_ops(user)
        booking = await self.bookings.get(booking_id)
        if not booking:
            raise errors.NotFoundError("Booking not found.")
        if booking.status != "requested":
            raise errors.ConflictError(f"Booking is already {booking.status}.")
        booking.vessel = confirmation.vessel
        booking.voyage = confirmation.voyage
        if confirmation.etd:
            shift = confirmation.etd - booking.etd
            booking.etd = confirmation.etd
            booking.eta = confirmation.eta or booking.eta + shift
        elif confirmation.eta:
            booking.eta = confirmation.eta
        booking.status = "confirmed"
        booking.confirmed_at = db.utcnow()
        booking.confirmed_by = user.email
        self.outbox.add(
            events.EventType.BOOKING_CONFIRMED,
            await self._confirmed_event(booking),
        )
        await self._session.commit()
        return booking

    async def cancel(
        self, user: auth.CurrentUser, booking_id: str, reason: str
    ) -> models.Booking:
        """Cancels a booking.

        Customers may cancel only while the booking is still a request; ops
        may cancel confirmed bookings too.

        Args:
            user: The caller.
            booking_id: The booking.
            reason: Why it is cancelled.

        Returns:
            The cancelled booking.

        Raises:
            errors.NotFoundError: The booking does not exist or is not
                visible.
            errors.ConflictError: The booking cannot be cancelled.
        """
        booking = await self.get_booking(user, booking_id)
        if booking.status != "requested" and not user.is_ops:
            raise errors.ConflictError(
                "This booking is confirmed with the carrier. Contact your ops"
                " team to cancel it."
            )
        if booking.status == "cancelled":
            raise errors.ConflictError("Booking is already cancelled.")
        booking.status = "cancelled"
        booking.cancel_reason = reason
        self.outbox.add(
            events.EventType.BOOKING_CANCELLED,
            events.BookingCancelled(
                booking_id=booking.id,
                booking_ref=booking.ref,
                company_id=booking.company_id,
                reason=reason,
            ),
        )
        await self._session.commit()
        return booking

    async def _confirmed_event(
        self, booking: models.Booking
    ) -> events.BookingConfirmed:
        via = (
            await self.get_port(booking.via_port) if booking.via_port else None
        )
        return events.BookingConfirmed(
            booking_id=booking.id,
            booking_ref=booking.ref,
            company_id=booking.company_id,
            contact_email=booking.requested_by_email,
            pol=booking.pol,
            pod=booking.pod,
            via=booking.via_port,
            pol_name=(await self.get_port(booking.pol)).name,
            pod_name=(await self.get_port(booking.pod)).name,
            via_name=via.name if via else None,
            carrier=booking.carrier,
            vessel=booking.vessel,
            voyage=booking.voyage,
            etd=booking.etd,
            eta=booking.eta,
            container_type=booking.container_type,
            quantity=booking.quantity,
            commodity=booking.commodity,
            incoterm=booking.incoterm,
            gross_weight_kg=booking.gross_weight_kg,
            cargo_value_cents=booking.cargo_value_cents,
            lines=[events.PriceLine(**line) for line in booking.lines],
        )
