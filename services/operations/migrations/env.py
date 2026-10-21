"""Alembic environment of the operations service."""

from halyard_common import migrations
from operations import models
from operations.core import config

migrations.run_migrations(models.Base.metadata, config.Settings())
