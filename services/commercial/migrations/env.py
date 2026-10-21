"""Alembic environment of the commercial service."""

from commercial import models
from commercial.core import config
from halyard_common import migrations

migrations.run_migrations(models.Base.metadata, config.Settings())
