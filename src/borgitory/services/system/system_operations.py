"""
System operations service implementations.

Concrete implementations of system operation protocols for production use.
"""

import os
import subprocess
import logging
from typing import Any, Optional
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from borgitory.protocols.system_protocol import (
    SystemOperationsProtocol,
    DatabaseOperationsProtocol,
    MigrationOperationsProtocol,
)
from borgitory.config_module import DATA_DIR, DATABASE_URL

logger = logging.getLogger(__name__)


class SystemOperations(SystemOperationsProtocol):
    """Production implementation of system operations."""

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directories recursively."""
        os.makedirs(path, exist_ok=exist_ok)

    def path_exists(self, path: str) -> bool:
        """Check if a path exists."""
        return os.path.exists(path)

    def get_data_dir(self) -> str:
        """Get the application data directory."""
        return DATA_DIR

    def import_resources(self) -> Any:
        """Import importlib.resources module."""
        from importlib import resources

        return resources

    def resources_files(self, package: str) -> Any:
        """Get package files using importlib.resources."""
        resources = self.import_resources()
        return resources.files(package)

    def path_truediv(self, base_path: Any, sub_path: str) -> Any:
        """Perform path / operation."""
        return base_path / sub_path

    def path_str(self, path: Any) -> str:
        """Convert path to string."""
        return str(path)

    def path_is_file(self, path: Any) -> bool:
        """Check if path is a file."""
        try:
            result = path.is_file()
            return bool(result)
        except (AttributeError, OSError):
            return False


class DatabaseOperations(DatabaseOperationsProtocol):
    """Production implementation of database operations."""

    async def get_current_revision(self) -> Optional[str]:
        """Get the current database revision."""
        try:
            # Create a synchronous engine for Alembic operations
            sync_engine = create_engine(
                DATABASE_URL, connect_args={"check_same_thread": False}
            )

            with sync_engine.connect() as connection:
                context = MigrationContext.configure(connection)
                return context.get_current_revision()
        except Exception as e:
            logger.error(f"Failed to get current revision: {e}")
            return None


class MigrationOperations(MigrationOperationsProtocol):
    """Production implementation of migration operations."""

    def run_alembic_upgrade(self, config_path: str) -> bool:
        """Run alembic upgrade command with proper environment setup."""
        try:
            logger.info("Running database migrations...")

            # Get database URL using the same logic as the main application
            database_url = self._get_sync_database_url()
            logger.info(f"Using database URL: {database_url}")

            # Get the directory containing the alembic.ini file
            config_dir = os.path.dirname(os.path.abspath(config_path))
            logger.info(f"Running alembic from directory: {config_dir}")

            # Run alembic upgrade using subprocess with proper environment
            result = subprocess.run(
                ["alembic", "-c", config_path, "upgrade", "head"],
                check=True,
                capture_output=True,
                text=True,
                cwd=config_dir,  # Set working directory to where alembic.ini is located
                timeout=60,  # Add timeout to prevent hanging
            )

            if result.returncode != 0:
                logger.error(
                    f"Database migration failed with exit code {result.returncode}"
                )
                if result.stderr:
                    logger.error(f"stderr: {result.stderr}")
                return False

            logger.info("Database migrations completed successfully")
            if result.stdout:
                logger.info(f"Migration output: {result.stdout}")
            if result.stderr:
                logger.info(f"Migration stderr: {result.stderr}")

            return True

        except subprocess.TimeoutExpired:
            logger.error("Migration timed out after 60 seconds")
            return False
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

    def _get_database_url(self) -> str:
        """Get database URL using the same logic as the main application."""

        return os.getenv("DATABASE_URL", DATABASE_URL)

    def _get_sync_database_url(self) -> str:
        """Get database URL using the same logic as the main application."""

        asyncUrl = self._get_database_url()
        syncUrl = asyncUrl.replace("+aiosqlite", "")
        return syncUrl
