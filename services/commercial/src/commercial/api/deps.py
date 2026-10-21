"""FastAPI dependencies that build the use-case classes per request."""

from typing import Annotated, TypeVar

import fastapi

from commercial import services
from halyard_common import dependencies

_ServiceT = TypeVar("_ServiceT", bound=services.CommercialService)


def _provider(cls: type[_ServiceT]):
    """Returns a FastAPI dependency that builds ``cls`` per request."""

    def provide(
        request: fastapi.Request, session: dependencies.Session
    ) -> _ServiceT:
        return cls(session, dependencies.get_settings(request))

    return provide


Quotes = Annotated[
    services.QuoteService, fastapi.Depends(_provider(services.QuoteService))
]


Bookings = Annotated[
    services.BookingService, fastapi.Depends(_provider(services.BookingService))
]


Rates = Annotated[
    services.RateService, fastapi.Depends(_provider(services.RateService))
]


Leads = Annotated[
    services.LeadService, fastapi.Depends(_provider(services.LeadService))
]
