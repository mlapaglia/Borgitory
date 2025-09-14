"""Alembic migration utilities for Borgitory."""

import logging
import os
from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from config import DATA_DIR
from models.database import engine

logger = logging.getLogger(__name__)


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    # Try multiple possible locations for alembic.ini
    possible_paths = [
        # Container environment (working directory is /app)
        Path("/app/alembic.ini"),
        # Local development (project root)
        Path(__file__).parent.parent.parent / "alembic.ini",
        # Current working directory
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

    # The database URL is now handled in env.py dynamically
    # No need to set it here as it's set in the env.py get_database_url function

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


def get_head_revision() -> str | None:
    """Get the head revision from migration scripts."""
    try:
        config = get_alembic_config()
        script_dir = ScriptDirectory.from_config(config)
        return script_dir.get_current_head()
    except Exception as e:
        logger.error(f"Failed to get head revision: {e}")
        return None


def database_needs_migration() -> bool:
    """Check if database needs migration."""
    current = get_current_revision()
    head = get_head_revision()

    if current is None and head is None:
        # No migrations exist yet
        return False

    return current != head


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


def create_migration(message: str, autogenerate: bool = True) -> bool:
    """Create a new migration."""
    try:
        config = get_alembic_config()

        logger.info(f"Creating migration: {message}")
        command.revision(config, message=message, autogenerate=autogenerate)
        logger.info("Migration created successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        return False


def stamp_database(revision: str = "head") -> bool:
    """Stamp the database with a specific revision without running migrations."""
    try:
        config = get_alembic_config()

        logger.info(f"Stamping database with revision: {revision}")
        command.stamp(config, revision)
        logger.info("Database stamped successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to stamp database: {e}")
        return False


def show_migration_history() -> None:
    """Show migration history."""
    try:
        config = get_alembic_config()
        command.history(config)
    except Exception as e:
        logger.error(f"Failed to show migration history: {e}")


def show_current_revision() -> None:
    """Show current database revision."""
    try:
        config = get_alembic_config()
        command.current(config)
    except Exception as e:
        logger.error(f"Failed to show current revision: {e}")
