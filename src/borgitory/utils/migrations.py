"""Alembic migration utilities for Borgitory."""

import logging
import os
import subprocess
from alembic.runtime.migration import MigrationContext

from borgitory.config_module import DATA_DIR

logger = logging.getLogger(__name__)


def get_current_revision() -> str | None:
    """Get the current database revision."""
    try:
        from borgitory.models.database import engine

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()
    except Exception as e:
        logger.error(f"Failed to get current revision: {e}")
        return None


def run_migrations() -> bool:
    """Run database migrations to the latest version using subprocess to avoid engine conflicts."""
    try:
        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)

        # Get the config path using the same logic as CLI
        from importlib import resources

        try:
            # Try to find alembic.ini in the package data
            package_dir = resources.files("borgitory")
            alembic_ini_path = package_dir / "alembic.ini"

            # Convert to string and check if file exists
            config_path_str = str(alembic_ini_path)
            if os.path.exists(config_path_str):
                config_path = config_path_str
            else:
                # Try checking with is_file() if available
                try:
                    if alembic_ini_path.is_file():
                        config_path = config_path_str
                    else:
                        config_path = "alembic.ini"
                except (AttributeError, OSError):
                    config_path = "alembic.ini"
        except (ImportError, AttributeError, TypeError, OSError):
            # Fallback for older Python versions or if resources not available
            config_path = "alembic.ini"

        logger.info("Running database migrations...")

        # Run alembic upgrade head with explicit config using subprocess
        result = subprocess.run(
            ["alembic", "-c", config_path, "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(
                f"Database migration failed with exit code {result.returncode}"
            )
            return False

        logger.info("Database migrations completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed with exit code {e.returncode}")
        if e.stdout:
            logger.error(f"stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error(
            "Alembic command not found! Make sure alembic is installed and available in your PATH"
        )
        return False
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
