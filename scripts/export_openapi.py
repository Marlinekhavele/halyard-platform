"""Writes each service's OpenAPI spec to ``docs/openapi/<service>.json``.

API clients (web apps, partner integrations) generate their types from these
files, so they never drift from the services.

    python scripts/export_openapi.py
"""

import importlib
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import dev_server  # noqa: E402  # pylint: disable=wrong-import-position


def main() -> None:
    """Exports every service's OpenAPI document."""
    os.environ.setdefault("SEED_DEMO_DATA", "false")
    dev_server.prepare_environment(
        pathlib.Path(tempfile.mkdtemp(prefix="halyard-openapi-"))
    )
    out = ROOT / "docs" / "openapi"
    out.mkdir(parents=True, exist_ok=True)
    services = {
        name: importlib.import_module(f"{name}.main").create_app()
        for name in dev_server.SERVICES
    }
    documents = {name: app.openapi() for name, app in services.items()}
    # Plus everything in one document, as served at /docs by the dev server.
    documents["halyard"] = dev_server.combined_openapi(services)
    for name, document in documents.items():
        spec = json.dumps(document, indent=2, ensure_ascii=False)
        (out / f"{name}.json").write_text(spec + "\n")
        print(f"wrote {out / name}.json")


if __name__ == "__main__":
    main()
