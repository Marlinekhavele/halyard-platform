"""Tests for halyard_common.openapi.merge."""

from halyard_common import openapi

REF = "#/components/schemas/"
ERROR = {"type": "object", "properties": {"detail": {"type": "string"}}}
BEARER = {"HTTPBearer": {"type": "http", "scheme": "bearer"}}


def _spec(paths: dict, schemas: dict) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "x", "version": "1"},
        "paths": paths,
        "components": {"schemas": schemas, "securitySchemes": BEARER},
    }


def _get(tag: str, op_id: str, ref: str) -> dict:
    return {
        "get": {
            "tags": [tag],
            "operationId": op_id,
            "responses": {
                "200": {
                    "content": {
                        "application/json": {"schema": {"$ref": REF + ref}}
                    }
                }
            },
        }
    }


COMMERCIAL = _spec(
    {
        "/quotes": _get("quotes", "list_quotes", "Item"),
        "/health": _get("system", "health", "Error"),
    },
    {
        "Item": {"type": "object", "properties": {"ref": {"type": "string"}}},
        "Error": ERROR,
    },
)
BILLING = _spec(
    {
        "/invoices": _get("invoices", "list_invoices", "Item"),
        "/health": _get("system", "health", "Error"),
    },
    {
        "Item": {
            "type": "object",
            "properties": {"number": {"type": "string"}},
        },
        "Error": ERROR,
    },
)


def test_paths_get_the_gateway_prefix():
    merged = openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    assert set(merged["paths"]) == {
        "/api/commercial/quotes",
        "/api/commercial/health",
        "/api/billing/invoices",
        "/api/billing/health",
    }


def test_tags_and_operation_ids_are_prefixed_and_unique():
    merged = openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    quotes = merged["paths"]["/api/commercial/quotes"]["get"]
    assert quotes["tags"] == ["commercial · quotes"]
    assert quotes["operationId"] == "commercial_list_quotes"
    ids = [
        op["operationId"]
        for ops in merged["paths"].values()
        for op in ops.values()
    ]
    assert len(ids) == len(set(ids))
    assert [t["name"] for t in merged["tags"]] == [
        "commercial · quotes",
        "commercial · system",
        "billing · invoices",
        "billing · system",
    ]


def test_identical_schemas_are_shared():
    merged = openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    assert merged["components"]["schemas"]["Error"] == ERROR
    assert "BillingError" not in merged["components"]["schemas"]


def test_clashing_schemas_are_renamed_and_references_follow():
    merged = openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    schemas = merged["components"]["schemas"]
    assert "ref" in schemas["Item"]["properties"]
    assert "number" in schemas["BillingItem"]["properties"]
    invoices = merged["paths"]["/api/billing/invoices"]["get"]
    schema = invoices["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert schema == {"$ref": REF + "BillingItem"}


def test_one_security_scheme_for_all_services():
    merged = openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    assert merged["components"]["securitySchemes"] == BEARER


def test_inputs_are_not_modified():
    before = str(BILLING)

    openapi.merge({"commercial": COMMERCIAL, "billing": BILLING})

    assert str(BILLING) == before
