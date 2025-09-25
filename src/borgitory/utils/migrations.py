"""Alembic migration utilities for Borgitory."""

import logging
import os
from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext

from borgitory.config_module import DATA_DIR
from borgitory.models.database import engine

logger = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    possible_paths = [
        Path("/app/alembic.ini"),
        Path(__file__).parent.parent.parent / "alembic.ini",
        Path.cwd() / "alembic.ini",
    ]

    alembic_ini_path = None
    for path in possible_paths:
        if path.exists():
            alembic_ini_path = path
            break

    if not alembic_ini_path:
        raise RuntimeError(
            f"Alembic configuration not found. Searched: {[str(p) for p in possible_paths]}"
        )

    config = Config(str(alembic_ini_path))

    return config


def get_current_revision() -> str | None:
    """Get the current database revision."""
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()
    except Exception as e:
        logger.error(f"Failed to get current revision: {e}")
        return None


def run_migrations() -> bool:
    """Run database migrations to the latest version."""
    try:
        config = get_alembic_config()

        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)

        logger.info("Running database migrations...")
        command.upgrade(config, "head")
        logger.info("Database migrations completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
