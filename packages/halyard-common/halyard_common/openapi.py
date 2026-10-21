"""Merges the services' OpenAPI documents into one.

Each service documents its own API. For a single Swagger UI, ``merge``
combines them: paths get the gateway prefix (``/api/<service>``), tags and
operation ids are prefixed with the service name, and schema names that two
services define differently are renamed, with every reference rewritten.
"""

import copy
from typing import Any

_REF_PREFIX = "#/components/schemas/"


def _renamed_ref(ref: str, renames: dict[str, str]) -> str:
    """Returns a ``$ref`` pointing at the schema's new name, if it has one."""
    if not ref.startswith(_REF_PREFIX):
        return ref
    name = ref.removeprefix(_REF_PREFIX)
    return _REF_PREFIX + renames.get(name, name)


def _rewrite_refs(node: Any, renames: dict[str, str]) -> Any:
    """Returns a copy of ``node`` with every schema reference renamed."""
    if isinstance(node, dict):
        return {
            key: (
                _renamed_ref(value, renames)
                if key == "$ref" and isinstance(value, str)
                else _rewrite_refs(value, renames)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(item, renames) for item in node]
    return node


def _tag(service: str, tag: str) -> str:
    return f"{service} · {tag}"


def merge(
    specs: dict[str, dict[str, Any]],
    title: str = "Halyard API",
    description: str = "",
    path_prefix: str = "/api/{service}",
) -> dict[str, Any]:
    """Combines several services' OpenAPI documents into one.

    Args:
        specs: OpenAPI document per service name, in display order.
        title: Title of the combined document.
        description: Description of the combined document.
        path_prefix: Prefix for each service's paths; ``{service}`` is
            replaced by the service name.

    Returns:
        One OpenAPI document covering every service.
    """
    merged: dict[str, Any] = {
        "openapi": next(iter(specs.values()), {}).get("openapi", "3.1.0"),
        "info": {
            "title": title,
            "version": "0.1.0",
            "description": description,
        },
        "paths": {},
        "components": {"schemas": {}, "securitySchemes": {}},
        "tags": [],
    }
    schemas = merged["components"]["schemas"]

    for service, original in specs.items():
        spec = copy.deepcopy(original)
        components = spec.get("components", {})

        # Rename only schemas that clash with a different definition.
        own = components.get("schemas", {})
        renames = {
            name: f"{service.capitalize()}{name}"
            for name, schema in own.items()
            if name in schemas and schemas[name] != _rewrite_refs(schema, {})
        }
        own = _rewrite_refs(own, renames)
        for name, schema in own.items():
            schemas[renames.get(name, name)] = schema
        merged["components"]["securitySchemes"].update(
            components.get("securitySchemes", {})
        )

        prefix = path_prefix.format(service=service)
        tags_seen: list[str] = []
        for path, operations in _rewrite_refs(
            spec.get("paths", {}), renames
        ).items():
            for operation in operations.values():
                if not isinstance(operation, dict):
                    continue
                operation["tags"] = [
                    _tag(service, t) for t in operation.get("tags") or ["other"]
                ]
                tags_seen += [
                    t for t in operation["tags"] if t not in tags_seen
                ]
                if "operationId" in operation:
                    operation["operationId"] = (
                        f"{service}_{operation['operationId']}"
                    )
            merged["paths"][prefix + path] = operations
        merged["tags"] += [
            {"name": t, "description": f"{service.capitalize()} service"}
            for t in tags_seen
        ]

    if not merged["components"]["securitySchemes"]:
        del merged["components"]["securitySchemes"]
    return merged
