"""Apply the unified schema migration. Implements: REQ-001, ADR-0001."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import settings


def run_migrations() -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", settings.sync_database_url.replace("%", "%%"))
    command.upgrade(config, "head")
