"""
Migration service with dependency injection.

This service handles database migrations using injected dependencies
for better testability and separation of concerns.
"""

import logging
from typing import Optional

from borgitory.protocols.system_protocol import (
    SystemOperationsProtocol,
    DatabaseOperationsProtocol,
    MigrationOperationsProtocol,
)

logger = logging.getLogger(__name__)


class MigrationService:
    """Service for handling database migrations with dependency injection."""

    def __init__(
        self,
        system_ops: SystemOperationsProtocol,
        database_ops: DatabaseOperationsProtocol,
        migration_ops: MigrationOperationsProtocol,
    ):
        """
        Initialize migration service with injected dependencies.

        Args:
            system_ops: System operations (file system, imports)
            database_ops: Database operations
            migration_ops: Migration execution operations
        """
        self.system_ops = system_ops
        self.database_ops = database_ops
        self.migration_ops = migration_ops

    async def get_current_revision(self) -> Optional[str]:
        """Get the current database revision."""
        try:
            return await self.database_ops.get_current_revision()
        except Exception as e:
            logger.error(f"Failed to get current revision: {e}")
            return None

    def run_migrations(self) -> bool:
        """Run database migrations to the latest version."""
        try:
            # Ensure data directory exists
            data_dir = self.system_ops.get_data_dir()
            self.system_ops.makedirs(data_dir, exist_ok=True)

            # Get the config path using the same logic as CLI
            config_path = self._get_alembic_config_path()

            # Run the migration
            return self.migration_ops.run_alembic_upgrade(config_path)

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    def _get_alembic_config_path(self) -> str:
        """Get the path to alembic.ini configuration file."""
        try:
            # Try to find alembic.ini in the package data
            package_dir = self.system_ops.resources_files("borgitory")
            alembic_ini_path = self.system_ops.path_truediv(package_dir, "alembic.ini")

            # Convert to string and check if file exists
            config_path_str = self.system_ops.path_str(alembic_ini_path)
            if self.system_ops.path_exists(config_path_str):
                return config_path_str
            else:
                # Try checking with is_file() if available
                if self.system_ops.path_is_file(alembic_ini_path):
                    return config_path_str
                else:
                    return "alembic.ini"

        except (ImportError, AttributeError, TypeError, OSError):
            # Fallback for older Python versions or if resources not available
            return "alembic.ini"
