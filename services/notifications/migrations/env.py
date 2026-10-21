"""Alembic environment of the notifications service."""

from halyard_common import migrations
from notifications import models
from notifications.core import config

migrations.run_migrations(models.Base.metadata, config.Settings())
