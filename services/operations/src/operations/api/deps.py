"""FastAPI dependencies that build the use-case classes per request."""

from typing import Annotated

import fastapi

from halyard_common import dependencies
from operations import services
from operations.core import config
from operations.core import storage as storage_lib


def _settings(request: fastapi.Request) -> config.Settings:
    settings = dependencies.get_settings(request)
    assert isinstance(settings, config.Settings)
    return settings


def get_shipment_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.ShipmentService:
    """Builds the shipment service for one request."""
    return services.ShipmentService(session, _settings(request))


def get_tracking_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.TrackingService:
    """Builds the tracking service for one request."""
    return services.TrackingService(session, _settings(request))


def get_storage(request: fastapi.Request) -> storage_lib.FileStorage:
    """Returns the app's document storage."""
    return request.app.state.storage


def get_document_service(
    request: fastapi.Request, session: dependencies.Session
) -> services.DocumentService:
    """Builds the document service for one request."""
    return services.DocumentService(
        session, _settings(request), get_storage(request)
    )


Shipments = Annotated[
    services.ShipmentService, fastapi.Depends(get_shipment_service)
]


Tracking = Annotated[
    services.TrackingService, fastapi.Depends(get_tracking_service)
]


Documents = Annotated[
    services.DocumentService, fastapi.Depends(get_document_service)
]
