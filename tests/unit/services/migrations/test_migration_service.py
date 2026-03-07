"""
Tests for the migration service with dependency injection.

Tests the migration service using proper dependency injection
instead of complex mocking.
"""

from unittest.mock import Mock
from typing import Any, Optional

from borgitory.services.migrations.migration_service import MigrationService
from borgitory.services.migrations.migration_factory import (
    create_migration_service_for_startup,
)
from borgitory.protocols.system_protocol import (
    SystemOperationsProtocol,
    DatabaseOperationsProtocol,
    MigrationOperationsProtocol,
)


class MockSystemOperations(SystemOperationsProtocol):
    """Mock implementation of system operations for testing."""

    def __init__(self) -> None:
        self.makedirs_calls: list[tuple[str, bool]] = []
        self.path_exists_return = True
        self.data_dir = "/test/data/dir"
        self.resources_package: Optional[str] = None
        self.resources_path: Optional[str] = None
        self.path_is_file_return = True

    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        self.makedirs_calls.append((path, exist_ok))

    def path_exists(self, path: str) -> bool:
        return self.path_exists_return

    def get_data_dir(self) -> str:
        return self.data_dir

    def import_resources(self) -> Any:
        if self.resources_package is None:
            raise ImportError("Resources not available")
        return Mock()

    def resources_files(self, package: str) -> Any:
        self.resources_package = package  # type: ignore[assignment]
        return Mock()

    def path_truediv(self, base_path: Any, sub_path: str) -> Any:
        mock_path = Mock()
        self.resources_path = mock_path  # type: ignore[assignment]
        return mock_path

    def path_str(self, path: Any) -> str:
        return "/package/alembic.ini"

    def path_is_file(self, path: Any) -> bool:
        return self.path_is_file_return


class MockDatabaseOperations(DatabaseOperationsProtocol):
    """Mock implementation of database operations for testing."""

    def __init__(self) -> None:
        self.current_revision = "abc123def456"
        self.should_raise = False

    async def get_current_revision(self) -> Optional[str]:
        if self.should_raise:
            raise Exception("Database error")
        return self.current_revision


class MockMigrationOperations(MigrationOperationsProtocol):
    """Mock implementation of migration operations for testing."""

    def __init__(self) -> None:
        self.run_calls: list[str] = []
        self.should_succeed = True

    def run_alembic_upgrade(self, config_path: str) -> bool:
        self.run_calls.append(config_path)
        return self.should_succeed


class TestMigrationService:
    """Test cases for MigrationService."""

    async def test_get_current_revision_success(self) -> None:
        """Test successful retrieval of current revision."""
        system_ops = MockSystemOperations()
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = await service.get_current_revision()

        assert result == "abc123def456"

    async def test_get_current_revision_none(self) -> None:
        """Test when no current revision exists."""
        system_ops = MockSystemOperations()
        database_ops = MockDatabaseOperations()
        database_ops.current_revision = None
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = await service.get_current_revision()

        assert result is None

    async def test_get_current_revision_error(self) -> None:
        """Test when database operation raises error."""
        system_ops = MockSystemOperations()
        database_ops = MockDatabaseOperations()
        database_ops.should_raise = True
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = await service.get_current_revision()

        assert result is None

    def test_run_migrations_success_with_package_config(self) -> None:
        """Test successful migration run with package config path."""
        system_ops = MockSystemOperations()
        system_ops.path_exists_return = True
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is True
        assert system_ops.makedirs_calls == [("/test/data/dir", True)]
        assert migration_ops.run_calls == ["/package/alembic.ini"]

    def test_run_migrations_success_with_fallback_config(self) -> None:
        """Test successful migration run with fallback config path."""
        system_ops = MockSystemOperations()
        system_ops.path_exists_return = False
        system_ops.path_is_file_return = False
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is True
        assert migration_ops.run_calls == ["alembic.ini"]

    def test_run_migrations_success_with_is_file_check(self) -> None:
        """Test successful migration run when using is_file() check."""
        system_ops = MockSystemOperations()
        system_ops.path_exists_return = False
        system_ops.path_is_file_return = True
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is True
        assert migration_ops.run_calls == ["/package/alembic.ini"]

    def test_run_migrations_failure(self) -> None:
        """Test migration failure."""
        system_ops = MockSystemOperations()
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()
        migration_ops.should_succeed = False

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is False

    def test_run_migrations_resources_import_error(self) -> None:
        """Test migration with resources import error."""
        system_ops = MockSystemOperations()

        def failing_resources_files(package: str) -> Any:
            raise ImportError("Resources not available")

        system_ops.resources_files = failing_resources_files  # type: ignore[assignment]
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is True
        assert migration_ops.run_calls == ["alembic.ini"]

    def test_run_migrations_makedirs_exception(self) -> None:
        """Test migration failure when data directory creation fails."""
        system_ops = MockSystemOperations()

        def failing_makedirs(path: str, exist_ok: bool = True) -> None:
            raise OSError("Permission denied")

        system_ops.makedirs = failing_makedirs  # type: ignore[assignment]
        database_ops = MockDatabaseOperations()
        migration_ops = MockMigrationOperations()

        service = MigrationService(system_ops, database_ops, migration_ops)
        result = service.run_migrations()

        assert result is False


class TestMigrationServiceFactory:
    """Test cases for migration service factory functions."""

    def test_create_migration_service_for_startup(self) -> None:
        """Test creating migration service for startup with production dependencies."""
        service = create_migration_service_for_startup()

        assert isinstance(service, MigrationService)
        assert service.system_ops is not None
        assert service.database_ops is not None
        assert service.migration_ops is not None

        # Test that it creates a new instance each time (no caching)
        service2 = create_migration_service_for_startup()
        assert service is not service2
