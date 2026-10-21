"""Alembic environment of the billing service."""

from billing import models
from billing.core import config
from halyard_common import migrations

migrations.run_migrations(models.Base.metadata, config.Settings())
