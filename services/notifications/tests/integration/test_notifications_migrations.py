"""Migrations must build exactly the schema the models describe."""

import pathlib

from halyard_common import testing
from notifications import models

ALEMBIC_INI = pathlib.Path(__file__).resolve().parents[2] / "alembic.ini"


def test_migrations_match_models(tmp_path):
    drift = testing.schema_drift(
        ALEMBIC_INI, testing.sqlite_url(tmp_path), models.Base.metadata
    )

    assert drift == [], "run: alembic revision --autogenerate -m '...'"
