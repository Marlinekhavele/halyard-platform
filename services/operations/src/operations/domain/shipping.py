"""Shipment rules: container numbers, milestones, documents, tracking codes.

Pure functions and constants with no database access.
"""

import datetime
import hashlib
import string

CARRIER_OWNER_CODES = {
    "Maersk": "MSK",
    "MSC": "MSC",
    "CMA CGM": "CMA",
    "Hapag-Lloyd": "HLX",
    "ONE": "ONE",
    "COSCO": "CSN",
    "Evergreen": "EGH",
}
DEFAULT_OWNER_CODE = "HLY"

# Ordered milestone codes. Tracking events move a shipment through these.
MILESTONES = [
    "BOOKED",
    "EMPTY_PICKUP",
    "GATE_IN",
    "LOADED",
    "DEPARTED",
    "TRANSSHIPMENT",
    "ARRIVED",
    "DISCHARGED",
    "CUSTOMS_RELEASED",
    "DELIVERED",
]
ORIGIN_EVENTS = frozenset({"EMPTY_PICKUP", "GATE_IN", "LOADED", "DEPARTED"})
TRACKING_EVENTS = frozenset(MILESTONES[1:]) | {"CUSTOMS_HOLD", "ETA_CHANGED"}

STATUS_AFTER = {
    "DEPARTED": "in_transit",
    "TRANSSHIPMENT": "in_transit",
    "ARRIVED": "at_port",
    "DISCHARGED": "at_port",
    "CUSTOMS_HOLD": "customs_hold",
    "CUSTOMS_RELEASED": "at_port",
    "DELIVERED": "delivered",
}

ALLOWED_UPLOAD_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "text/csv",
    }
)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Documents the customer still has to act on.
OPEN_FOR_CUSTOMER = frozenset({"required", "review"})

TEU_PER_CONTAINER = {"20DV": 1, "40DV": 2, "40HC": 2, "40RF": 2}


def _letter_values() -> dict[str, int]:
    """ISO 6346 letter values: 10 upwards, skipping multiples of 11."""
    values: dict[str, int] = {}
    n = 10
    for letter in string.ascii_uppercase:
        if n % 11 == 0:
            n += 1
        values[letter] = n
        n += 1
    return values


_LETTER_VALUES = _letter_values()


def owner_code(carrier: str) -> str:
    """Returns the three-letter container owner code of a carrier.

    Args:
        carrier: The carrier name.

    Returns:
        The owner code; Halyard's own for unknown carriers.
    """
    return CARRIER_OWNER_CODES.get(carrier, DEFAULT_OWNER_CODE)


def iso6346_check_digit(first10: str) -> int:
    """Computes the ISO 6346 check digit.

    Args:
        first10: Owner code, category letter and six-digit serial.

    Returns:
        The check digit, 0 to 9.
    """
    total = sum(
        (int(c) if c.isdigit() else _LETTER_VALUES[c]) * (2**i)
        for i, c in enumerate(first10)
    )
    return (total % 11) % 10


def is_valid_container_number(number: str) -> bool:
    """Checks format and check digit of a container number.

    Args:
        number: The number; spaces and case are ignored.

    Returns:
        True if it is a valid ISO 6346 number.
    """
    number = number.replace(" ", "").upper()
    return (
        len(number) == 11
        and number[:4].isalpha()
        and number[4:].isdigit()
        and iso6346_check_digit(number[:10]) == int(number[10])
    )


def container_numbers(carrier: str, seed: str, count: int) -> list[str]:
    """Generates placeholder container numbers in valid ISO 6346 format.

    Used until the carrier releases the real numbers. The same seed always
    gives the same numbers.

    Args:
        carrier: Determines the owner code.
        seed: Usually the booking id.
        count: How many numbers.

    Returns:
        The container numbers.
    """
    owner = owner_code(carrier) + "U"
    base = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    numbers = []
    for i in range(count):
        serial = f"{(base // (i + 1)) % 1_000_000:06d}"
        first10 = owner + serial
        numbers.append(first10 + str(iso6346_check_digit(first10)))
    return numbers


def milestone_plan(
    *,
    carrier: str,
    vessel: str,
    pol_name: str,
    pod_name: str,
    via_name: str | None,
    etd: datetime.date,
    eta: datetime.date,
) -> list[tuple[str, str, datetime.date]]:
    """Plans every milestone of a shipment.

    Args:
        carrier: The carrier name.
        vessel: The vessel name.
        pol_name: Name of the port of loading.
        pod_name: Name of the port of discharge.
        via_name: Name of the transshipment port, if any.
        etd: Departure date.
        eta: Arrival date.

    Returns:
        ``(code, label, planned date)`` in chronological order.
    """
    days = datetime.timedelta
    transit = (eta - etd).days
    plan = [
        ("BOOKED", f"Booking confirmed with {carrier}", etd - days(10)),
        ("EMPTY_PICKUP", "Empty containers picked up", etd - days(6)),
        ("GATE_IN", f"Gated in at {pol_name}", etd - days(3)),
        ("LOADED", f"Loaded on {vessel}", etd - days(1)),
        ("DEPARTED", f"Departed {pol_name}", etd),
    ]
    if via_name:
        plan.append(
            (
                "TRANSSHIPMENT",
                f"Transshipment at {via_name}",
                etd + days(round(transit * 0.55)),
            )
        )
    plan += [
        ("ARRIVED", f"Arrived at {pod_name}", eta),
        ("DISCHARGED", "Discharged from vessel", eta + days(1)),
        ("CUSTOMS_RELEASED", "Customs cleared", eta + days(2)),
        ("DELIVERED", "Delivered to consignee", eta + days(4)),
    ]
    return plan


def required_documents(
    etd: datetime.date, container_type: str
) -> list[tuple[str, str, str, datetime.date | None]]:
    """Lists the documents a shipment needs.

    Args:
        etd: Departure date; due dates are counted back from it.
        container_type: Reefers need temperature instructions.

    Returns:
        ``(doc_type, label, initial status, due date)`` in display order.
    """
    days = datetime.timedelta
    docs = [
        ("COMMERCIAL_INVOICE", "Commercial invoice", "required", etd - days(3)),
        ("PACKING_LIST", "Packing list", "required", etd - days(3)),
        (
            "SHIPPING_INSTRUCTIONS",
            "Shipping instructions",
            "required",
            etd - days(3),
        ),
        (
            "VGM",
            "VGM declaration (verified gross mass)",
            "required",
            etd - days(2),
        ),
        ("BILL_OF_LADING", "Bill of lading", "not_due", None),
    ]
    if container_type == "40RF":
        docs.insert(
            2,
            (
                "TEMPERATURE_INSTRUCTIONS",
                "Reefer temperature instructions",
                "required",
                etd - days(4),
            ),
        )
    return docs


def basic_document_checks(content_type: str, data: bytes) -> list[dict]:
    """Runs quick automatic checks on an upload, shown to ops.

    This is the place to add AI extraction later, for example reading the
    invoice and comparing consignee, EORI and totals with the booking.

    Args:
        content_type: The declared MIME type.
        data: The file content.

    Returns:
        ``{"check": description, "ok": passed}`` per check.
    """
    checks = [
        {
            "check": "File type accepted",
            "ok": content_type in ALLOWED_UPLOAD_TYPES,
        },
        {"check": "File is not empty", "ok": len(data) > 0},
        {"check": "Under 20 MB", "ok": len(data) <= MAX_UPLOAD_BYTES},
    ]
    if content_type == "application/pdf":
        checks.append(
            {"check": "Looks like a valid PDF", "ok": data[:5] == b"%PDF-"}
        )
    return checks


def bill_of_lading_number(
    carrier: str, shipment_ref: str, departed: datetime.datetime
) -> str:
    """Builds a placeholder bill of lading number on departure.

    Args:
        carrier: The carrier name.
        shipment_ref: The shipment reference.
        departed: Departure time.

    Returns:
        The number.
    """
    return f"{owner_code(carrier)}U{shipment_ref[-5:]}{departed:%m%d}"


def at_nine_utc(day: datetime.date) -> datetime.datetime:
    """Returns 09:00 UTC on a day; used for inferred milestone times.

    Args:
        day: The day.

    Returns:
        The timestamp.
    """
    return datetime.datetime(
        day.year, day.month, day.day, 9, 0, tzinfo=datetime.UTC
    )
