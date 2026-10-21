"""Tests for the pure shipment rules in operations.domain."""

import datetime

from operations.domain import shipping

ETD = datetime.date(2026, 10, 1)


def _codes(plan) -> list[str]:
    return [code for code, _, _ in plan]


def test_iso6346_known_numbers():
    # Published examples with known check digits.
    assert shipping.iso6346_check_digit("CSQU305438") == 3
    assert shipping.is_valid_container_number("MSKU 907032 3")
    assert not shipping.is_valid_container_number("MSKU9070324")
    assert not shipping.is_valid_container_number("MSKU90703")


def test_generated_numbers_are_valid_and_stable():
    numbers = shipping.container_numbers("Hapag-Lloyd", "booking-1", 3)

    assert len(set(numbers)) == 3
    assert all(n.startswith("HLXU") for n in numbers)
    assert all(shipping.is_valid_container_number(n) for n in numbers)
    assert numbers == shipping.container_numbers("Hapag-Lloyd", "booking-1", 3)


def test_unknown_carrier_uses_halyard_owner_code():
    [number] = shipping.container_numbers("Unknown Lines", "b", 1)

    assert number.startswith("HLYU")


def test_milestone_plan_with_transshipment():
    plan = shipping.milestone_plan(
        carrier="MSC",
        vessel="MSC Rhea",
        pol_name="Shanghai",
        pod_name="Hamburg",
        via_name="Singapore",
        etd=ETD,
        eta=datetime.date(2026, 11, 3),
    )

    codes = _codes(plan)
    assert codes.index("TRANSSHIPMENT") == codes.index("DEPARTED") + 1
    assert codes[-1] == "DELIVERED"
    dates = [d for _, _, d in plan]
    assert dates == sorted(dates)


def test_direct_route_has_no_transshipment():
    plan = shipping.milestone_plan(
        carrier="ONE",
        vessel="ONE Harmony",
        pol_name="Busan",
        pod_name="Rotterdam",
        via_name=None,
        etd=ETD,
        eta=datetime.date(2026, 11, 1),
    )

    assert "TRANSSHIPMENT" not in _codes(plan)
    assert _codes(plan) == [
        c for c in shipping.MILESTONES if c != "TRANSSHIPMENT"
    ]


def test_reefer_needs_temperature_instructions():
    def doc_types(container_type: str) -> list[str]:
        return [t for t, *_ in shipping.required_documents(ETD, container_type)]

    assert "TEMPERATURE_INSTRUCTIONS" not in doc_types("40HC")
    assert "TEMPERATURE_INSTRUCTIONS" in doc_types("40RF")


def test_bill_of_lading_is_not_due_until_shared():
    required = shipping.required_documents(ETD, "40HC")
    docs = {doc_type: (status, due) for doc_type, _, status, due in required}

    assert docs["BILL_OF_LADING"] == ("not_due", None)
    assert docs["VGM"] == ("required", ETD - datetime.timedelta(days=2))


def test_document_checks():
    good = shipping.basic_document_checks("application/pdf", b"%PDF-1.4 ...")
    fake_pdf = shipping.basic_document_checks("application/pdf", b"hello")
    exe = shipping.basic_document_checks("application/x-msdownload", b"MZ")

    assert all(c["ok"] for c in good)
    assert not all(c["ok"] for c in fake_pdf)
    assert not exe[0]["ok"]


def test_bill_of_lading_number():
    departed = datetime.datetime(2026, 10, 9, tzinfo=datetime.UTC)

    number = shipping.bill_of_lading_number("Maersk", "HLY-26-00042", departed)

    assert number == "MSKU000421009"
