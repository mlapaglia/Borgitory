"""
Dependency injection functions for migration services.

Following the codebase pattern of individual dependency functions.
"""

from borgitory.services.migrations.migration_service import MigrationService
from borgitory.services.system.system_operations import (
    SystemOperations,
    DatabaseOperations,
    MigrationOperations,
)
from borgitory.protocols.system_protocol import (
    SystemOperationsProtocol,
    DatabaseOperationsProtocol,
    MigrationOperationsProtocol,
)


def get_system_operations() -> SystemOperationsProtocol:
    """Get system operations implementation."""
    return SystemOperations()


def get_database_operations() -> DatabaseOperationsProtocol:
    """Get database operations implementation."""
    return DatabaseOperations()


def get_migration_operations() -> MigrationOperationsProtocol:
    """Get migration operations implementation."""
    return MigrationOperations()


def create_migration_service_for_startup() -> MigrationService:
    """
    Create MigrationService for application startup.

    This creates a one-time migration service for database initialization.
    Uses the same pattern as other startup services.
    """
    # Resolve all dependencies directly (not via FastAPI DI)
    system_ops = get_system_operations()
    database_ops = get_database_operations()
    migration_ops = get_migration_operations()

    return MigrationService(
        system_ops=system_ops,
        database_ops=database_ops,
        migration_ops=migration_ops,
    )
