"""Ports, prices, quotes and turning a quote into a booking."""

from collections.abc import Sequence
import datetime

from commercial import models
from commercial import schemas
from commercial.domain import pricing
from commercial.services import base
from halyard_common import auth
from halyard_common import errors
from halyard_common import events


class QuoteService(base.CommercialService):
    """Ports, prices, quotes and turning a quote into a booking."""

    async def list_ports(self) -> Sequence[models.Port]:
        """Returns every served port, alphabetically."""
        return await self.ports.list_by_name()

    async def price(
        self, request: schemas.QuoteCreate
    ) -> list[pricing.PricedOption]:
        """Prices a request against current rates.

        Args:
            request: The price request.

        Returns:
            Up to three options; empty if no rate matches.

        Raises:
            errors.InvalidRequestError: A port is not served.
        """
        pol = await self.get_port(request.pol)
        pod = await self.get_port(request.pod)
        today = self.today()
        rates = await self.rates.find_bookable(
            pol.region, pod.region, request.container_type, today
        )
        surcharges = await self.surcharges.list_sorted()
        quote_request = pricing.QuoteRequest(
            container_type=request.container_type,
            quantity=request.quantity,
            ready_date=max(request.ready_date, today),
            cargo_value_cents=request.cargo_value_cents,
            customs=request.customs,
            trucking=request.trucking,
            insurance=request.insurance,
        )
        return pricing.build_options(
            [_rate_input(r) for r in rates],
            [_surcharge_input(s) for s in surcharges],
            quote_request,
        )

    async def create_quote(
        self, user: auth.CurrentUser, request: schemas.QuoteCreate
    ) -> models.Quote:
        """Prices a request and saves it as a bookable quote.

        Args:
            user: The caller; the quote belongs to their company.
            request: The price request.

        Returns:
            The saved quote with its options.

        Raises:
            errors.InvalidRequestError: A port is not served or no rate
                matches.
        """
        options = await self.price(request)
        if not options:
            raise errors.InvalidRequestError(
                "We have no rates on this route for this container type yet."
                " Our team can quote it manually."
            )
        today = self.today()
        quote = models.Quote(
            ref=await self.quotes.next_ref(today),
            company_id=user.company_id,
            created_by=user.id,
            created_by_email=user.email,
            valid_until=today
            + datetime.timedelta(days=self._settings.quote_validity_days),
            **request.model_dump(),
        )
        quote.options = [
            _quote_option(position, option)
            for position, option in enumerate(options)
        ]
        await self.quotes.add(quote)
        await self._session.commit()
        await self._session.refresh(quote)
        return quote

    async def list_quotes(
        self, user: auth.CurrentUser, limit: int
    ) -> Sequence[models.Quote]:
        """Returns the newest quotes the caller may see.

        Args:
            user: The caller.
            limit: Maximum number of quotes.

        Returns:
            The quotes, newest first.
        """
        return await self.quotes.list_recent(base.company_scope(user), limit)

    async def get_quote(
        self, user: auth.CurrentUser, quote_id: str
    ) -> models.Quote:
        """Returns a quote the caller may see.

        Args:
            user: The caller.
            quote_id: The quote.

        Returns:
            The quote.

        Raises:
            errors.NotFoundError: The quote does not exist or is not visible.
        """
        quote = await self.quotes.get(quote_id)
        if not quote or not user.can_see_company(quote.company_id):
            raise errors.NotFoundError("Quote not found.")
        return quote

    async def book_option(
        self,
        user: auth.CurrentUser,
        quote_id: str,
        option_id: str,
        details: schemas.AcceptOption,
    ) -> models.Booking:
        """Books one option of the caller's quote.

        Creates a booking request for the ops team to confirm with the
        carrier.

        Args:
            user: The caller; must belong to the quote's company.
            quote_id: The quote.
            option_id: The chosen option.
            details: Weight, supplier and notes.

        Returns:
            The new booking.

        Raises:
            errors.NotFoundError: The quote or option does not exist.
            errors.ConflictError: The quote is already booked or expired.
        """
        quote = await self.quotes.get(quote_id)
        if not quote or quote.company_id != user.company_id:
            raise errors.NotFoundError("Quote not found.")
        if quote.status != "open":
            raise errors.ConflictError("This quote has already been booked.")
        today = self.today()
        if quote.valid_until < today:
            raise errors.ConflictError(
                "This quote has expired. Request a new quote for current"
                " prices."
            )
        option = next((o for o in quote.options if o.id == option_id), None)
        if not option:
            raise errors.NotFoundError("Option not found on this quote.")
        # The check above is only a fast path; this claim is the real guard
        # against two simultaneous bookings of the same quote.
        if not await self.quotes.claim_for_booking(quote.id):
            await self._session.rollback()
            raise errors.ConflictError("This quote has already been booked.")

        booking = await self.bookings.add(
            models.Booking(
                ref=await self.bookings.next_ref(today),
                quote_id=quote.id,
                option_id=option.id,
                company_id=quote.company_id,
                requested_by=user.id,
                requested_by_email=user.email,
                pol=quote.pol,
                pod=quote.pod,
                via_port=option.via_port,
                carrier=option.carrier,
                container_type=quote.container_type,
                quantity=quote.quantity,
                commodity=quote.commodity,
                incoterm=quote.incoterm,
                gross_weight_kg=details.gross_weight_kg,
                cargo_value_cents=quote.cargo_value_cents,
                supplier_name=details.supplier_name,
                notes=details.notes,
                etd=option.etd,
                eta=option.eta,
                total_sell_cents=option.total_sell_cents,
                total_cost_cents=option.total_cost_cents,
                lines=option.lines,
            )
        )
        self.outbox.add(
            events.EventType.BOOKING_REQUESTED,
            events.BookingRequested(
                booking_id=booking.id,
                booking_ref=booking.ref,
                company_id=booking.company_id,
                requested_by_email=user.email,
                pol=booking.pol,
                pod=booking.pod,
                carrier=booking.carrier,
                container_type=booking.container_type,
                quantity=booking.quantity,
                etd=booking.etd,
                total_sell_cents=booking.total_sell_cents,
            ),
        )
        await self._session.commit()
        return booking


def _rate_input(rate: models.Rate) -> pricing.RateInput:
    return pricing.RateInput(
        id=rate.id,
        carrier=rate.carrier,
        service=rate.service,
        via_port=rate.via_port,
        container_type=rate.container_type,
        buy_cents=rate.buy_cents,
        sell_cents=rate.sell_cents,
        transit_days=rate.transit_days,
        sailing_weekday=rate.sailing_weekday,
        co2_factor=rate.co2_factor,
    )


def _surcharge_input(surcharge: models.Surcharge) -> pricing.SurchargeInput:
    return pricing.SurchargeInput(
        code=surcharge.code,
        label=surcharge.label,
        basis=surcharge.basis,
        sell_value=surcharge.sell_value,
        cost_value=surcharge.cost_value,
        min_sell_cents=surcharge.min_sell_cents,
        min_cost_cents=surcharge.min_cost_cents,
        container_type=surcharge.container_type,
        option=surcharge.option,
        sort=surcharge.sort,
    )


def _quote_option(
    position: int, option: pricing.PricedOption
) -> models.QuoteOption:
    return models.QuoteOption(
        position=position,
        label=option.label,
        rate_id=option.rate.id,
        carrier=option.rate.carrier,
        service=option.rate.service,
        via_port=option.rate.via_port,
        etd=option.etd,
        eta=option.eta,
        transit_days=option.transit_days,
        co2_kg=option.co2_kg,
        total_sell_cents=option.total_sell_cents,
        total_cost_cents=option.total_cost_cents,
        lines=[line.as_dict() for line in option.lines],
    )
