"""Alembic environment of the accounts service."""

from accounts import models
from accounts.core import config
from halyard_common import migrations

migrations.run_migrations(models.Base.metadata, config.Settings())
