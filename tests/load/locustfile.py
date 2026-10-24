"""Load scenarios for the Halyard API.

Read-only traffic is the default. Quote creation and booking are opt-in because
those scenarios create persistent business data and trigger downstream events.
"""

import datetime
import os
import urllib.parse

import locust
import locust.exception

API_URL = os.getenv("HALYARD_API_URL", "http://127.0.0.1:8080").rstrip("/")
LOGIN_EMAIL = os.getenv("HALYARD_LOAD_LOGIN_EMAIL", "")
LOGIN_PASSWORD = os.getenv("HALYARD_LOAD_LOGIN_PASSWORD", "")
ORIGIN_PORT = os.getenv("HALYARD_LOAD_POL", "DEHAM").upper()
DESTINATION_PORT = os.getenv("HALYARD_LOAD_POD", "USNYC").upper()
CONTAINER_TYPE = os.getenv("HALYARD_LOAD_CONTAINER_TYPE", "20DV").upper()
INCLUDE_WRITES = os.getenv("HALYARD_LOAD_INCLUDE_WRITES", "false").lower() in {
    "1",
    "true",
    "yes",
}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_VALID_CONTAINER_TYPES = {"20DV", "40DV", "40HC", "40RF"}
if CONTAINER_TYPE not in _VALID_CONTAINER_TYPES:
    raise RuntimeError(
        "HALYARD_LOAD_CONTAINER_TYPE must be one of 20DV, 40DV, 40HC or 40RF."
    )


def _validate_target(api_url: str) -> None:
    """Prevents remote load runs without an explicit staging acknowledgement.

    Args:
        api_url: The host Locust will send requests to.

    Raises:
        RuntimeError: If a remote target is not explicitly declared staging.
    """
    parsed_url = urllib.parse.urlparse(api_url)
    hostname = parsed_url.hostname
    if not hostname:
        raise RuntimeError("HALYARD_API_URL must be an absolute URL.")
    if hostname in _LOCAL_HOSTS:
        return
    if (
        os.getenv("HALYARD_LOAD_TARGET", "").lower() != "staging"
        or os.getenv("HALYARD_LOAD_ALLOW_REMOTE", "").lower() != "true"
    ):
        raise RuntimeError(
            "Remote load tests require HALYARD_LOAD_TARGET=staging and "
            "HALYARD_LOAD_ALLOW_REMOTE=true. Do not run stress tests against "
            "production."
        )
    if parsed_url.scheme != "https":
        raise RuntimeError("Remote load tests must use HTTPS.")


if not LOGIN_EMAIL or not LOGIN_PASSWORD:
    raise RuntimeError(
        "Set HALYARD_LOAD_LOGIN_EMAIL and HALYARD_LOAD_LOGIN_PASSWORD "
        "to a dedicated test account before starting Locust."
    )
_validate_target(API_URL)


def _quote_payload() -> dict[str, object]:
    """Builds valid, non-sensitive quote data for the load-test account."""
    return {
        "pol": ORIGIN_PORT,
        "pod": DESTINATION_PORT,
        "container_type": CONTAINER_TYPE,
        "quantity": 1,
        "ready_date": (
            datetime.date.today() + datetime.timedelta(days=14)
        ).isoformat(),
        "incoterm": "FOB",
        "commodity": "Load-test general cargo",
        "cargo_value_cents": 0,
        "customs": False,
        "trucking": False,
        "insurance": False,
    }


class HalyardImporterUser(locust.HttpUser):
    """Represents an authenticated importer using common read workflows."""

    host = API_URL
    wait_time = locust.between(1, 3)

    def on_start(self) -> None:
        """Signs in once for each simulated user and stores its bearer token."""
        _validate_target(self.host)
        with self.client.post(
            "/api/accounts/auth/login",
            json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
            name="POST /api/accounts/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Login failed with HTTP {response.status_code}"
                )
                raise locust.exception.StopUser()
            try:
                token = response.json().get("access_token")
            except ValueError:
                token = None
            if not token:
                response.failure("Login response did not include access_token")
                raise locust.exception.StopUser()
            self.client.headers.update({"Authorization": f"Bearer {token}"})
            response.success()

    def _get_ok(self, path: str, name: str) -> None:
        """Issues a GET request and records unexpected responses as failures."""
        with self.client.get(path, name=name, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")

    @locust.task(5)
    def list_quotes(self) -> None:
        """Exercises the main importer quote-list read path."""
        self._get_ok(
            "/api/commercial/quotes?limit=50", "GET /api/commercial/quotes"
        )

    @locust.task(4)
    def estimate_quote(self) -> None:
        """Exercises quote pricing without saving a quote or booking it."""
        with self.client.post(
            "/api/commercial/quotes/estimate",
            json=_quote_payload(),
            name="POST /api/commercial/quotes/estimate",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                estimate = response.json()
            except ValueError:
                response.failure("Estimate response was not valid JSON")
                return
            if not estimate.get("options"):
                response.failure(
                    "No price options returned; check the test route rates."
                )

    @locust.task(3)
    def list_shipments(self) -> None:
        """Exercises shipment visibility for the authenticated company."""
        self._get_ok(
            "/api/operations/shipments", "GET /api/operations/shipments"
        )

    @locust.task(2)
    def list_invoices(self) -> None:
        """Exercises invoice-list reads without changing invoice state."""
        self._get_ok("/api/billing/invoices", "GET /api/billing/invoices")

    @locust.task(2)
    def list_notifications(self) -> None:
        """Exercises notification-list reads."""
        self._get_ok(
            "/api/notifications/notifications?limit=50",
            "GET /api/notifications/notifications",
        )

    @locust.task(2)
    def get_company_profile(self) -> None:
        """Exercises the current company's authenticated profile endpoint."""
        self._get_ok(
            "/api/accounts/companies/me", "GET /api/accounts/companies/me"
        )

    @locust.task(1)
    def list_ports(self) -> None:
        """Exercises the public port/reference-data endpoint."""
        self._get_ok("/api/commercial/ports", "GET /api/commercial/ports")

    if INCLUDE_WRITES:

        @locust.task(1)
        def create_and_book_quote(self) -> None:
            """Creates a fresh quote and books its first available option.

            This task is registered only when HALYARD_LOAD_INCLUDE_WRITES=true.
            It mutates data and can trigger shipment, invoice and notification
            events, so use a dedicated staging environment and test account.
            """
            with self.client.post(
                "/api/commercial/quotes",
                json=_quote_payload(),
                name="POST /api/commercial/quotes [write]",
                catch_response=True,
            ) as response:
                if response.status_code != 201:
                    response.failure(f"HTTP {response.status_code}")
                    return
                try:
                    quote = response.json()
                except ValueError:
                    response.failure("Quote response was not valid JSON")
                    return

                quote_id = quote.get("id")
                options = quote.get("options", [])
                option = next(
                    (item for item in options if item.get("id")),
                    None,
                )
                if not quote_id or not option:
                    response.failure(
                        "Quote has no bookable option; check route rates."
                    )
                    return
                response.success()

            with self.client.post(
                f"/api/commercial/quotes/{quote_id}/options/"
                f"{option['id']}/book",
                json={"gross_weight_kg": 12000, "supplier_name": "Load test"},
                name="POST quote option booking [write]",
                catch_response=True,
            ) as response:
                if response.status_code != 201:
                    response.failure(f"HTTP {response.status_code}")
