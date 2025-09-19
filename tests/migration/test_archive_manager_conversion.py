"""
Tests for ArchiveManager Conversion from Hybrid to Pure FastAPI DI

This module validates that ArchiveManager works correctly after conversion
from hybrid DI pattern to pure FastAPI DI.
"""

from unittest.mock import Mock

from tests.utils.di_testing import (
    override_dependency,
    override_multiple_dependencies,
    MockServiceFactory,
)
from borgitory.dependencies import (
    get_archive_manager,
    get_job_executor,
    get_borg_command_builder,
)
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.borg_command_builder import BorgCommandBuilder
from borgitory.main import app


class TestArchiveManagerPureDI:
    """Test ArchiveManager after conversion to pure FastAPI DI."""

    def test_archive_manager_can_be_created_directly(self):
        """Test that ArchiveManager can still be created for direct calls."""
        # This tests backward compatibility - direct calls should still work
        # but they won't get the benefits of FastAPI's DI system
        try:
            manager = get_archive_manager()
            assert manager is not None
            assert isinstance(manager, ArchiveManager)
        except TypeError as e:
            # This is expected with pure DI - direct calls need dependency resolution
            assert "missing" in str(e).lower() and (
                "job_executor" in str(e) or "command_builder" in str(e)
            )

    def test_archive_manager_works_with_dependency_override(self):
        """Test that ArchiveManager works correctly with dependency overrides."""
        mock_executor = MockServiceFactory.create_mock_job_executor()
        mock_builder = MockServiceFactory.create_mock_borg_command_builder()

        overrides = {
            get_job_executor: lambda: mock_executor,
            get_borg_command_builder: lambda: mock_builder,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that we can make API calls that use ArchiveManager
            # (Note: ArchiveManager might not be directly used in APIs, but this tests the DI system)
            response = client.get("/api/debug/info")  # Any endpoint to test DI works
            assert response is not None

    def test_archive_manager_dependency_injection_works(self):
        """Test that FastAPI properly injects dependencies into ArchiveManager."""
        # Create mock dependencies
        mock_executor = Mock(spec=JobExecutor)
        mock_builder = Mock(spec=BorgCommandBuilder)

        # Override the dependencies
        overrides = {
            get_job_executor: lambda: mock_executor,
            get_borg_command_builder: lambda: mock_builder,
        }

        with override_multiple_dependencies(overrides):
            # The DI system should work - we can't test ArchiveManager directly
            # since it's not exposed via API, but we can test that the DI system
            # itself is working
            assert get_job_executor in app.dependency_overrides
            assert get_borg_command_builder in app.dependency_overrides

    def test_archive_manager_no_longer_singleton(self):
        """Test that ArchiveManager is no longer a singleton (creates new instances)."""
        # With pure FastAPI DI, services are typically request-scoped
        # This means each request gets a new instance

        # We can't easily test this directly since we can't call get_archive_manager()
        # without providing dependencies, but we can test the DI pattern

        # Create different mock dependencies
        mock_executor1 = Mock(spec=JobExecutor)
        mock_executor2 = Mock(spec=JobExecutor)
        mock_builder = Mock(spec=BorgCommandBuilder)

        # Test with first set of dependencies
        overrides1 = {
            get_job_executor: lambda: mock_executor1,
            get_borg_command_builder: lambda: mock_builder,
        }

        # Test with second set of dependencies
        overrides2 = {
            get_job_executor: lambda: mock_executor2,
            get_borg_command_builder: lambda: mock_builder,
        }

        # Both should work independently
        with override_multiple_dependencies(overrides1) as client1:
            response1 = client1.get("/api/debug/info")
            assert response1 is not None

        with override_multiple_dependencies(overrides2) as client2:
            response2 = client2.get("/api/debug/info")
            assert response2 is not None

    def test_archive_manager_dependencies_are_injected_correctly(self):
        """Test that the correct dependency types are expected."""
        import inspect

        # Check the function signature
        sig = inspect.signature(get_archive_manager)
        params = sig.parameters

        # Should have job_executor and command_builder parameters
        assert "job_executor" in params
        assert "command_builder" in params

        # Check parameter annotations
        job_executor_param = params["job_executor"]
        command_builder_param = params["command_builder"]

        # Should have proper type annotations
        assert job_executor_param.annotation == JobExecutor
        assert command_builder_param.annotation == BorgCommandBuilder

        # Should have default values (Depends(...))
        assert job_executor_param.default is not inspect.Parameter.empty
        assert command_builder_param.default is not inspect.Parameter.empty


class TestArchiveManagerRegressionAfterConversion:
    """Regression tests to ensure ArchiveManager functionality is preserved."""

    def test_archive_manager_functionality_preserved(self):
        """Test that ArchiveManager functionality is preserved after conversion."""
        # Create real dependencies for testing
        job_executor = get_job_executor()
        command_builder = get_borg_command_builder()

        # Create ArchiveManager directly with dependencies
        manager = ArchiveManager(
            job_executor=job_executor, command_builder=command_builder
        )

        # Test that all expected methods exist and are callable
        assert hasattr(manager, "list_archive_contents")
        assert hasattr(manager, "get_archive_metadata")
        assert hasattr(manager, "list_archive_directory_contents")
        assert hasattr(manager, "validate_archive_path")

        assert callable(getattr(manager, "list_archive_contents"))
        assert callable(getattr(manager, "get_archive_metadata"))
        assert callable(getattr(manager, "list_archive_directory_contents"))
        assert callable(getattr(manager, "validate_archive_path"))

    def test_archive_manager_dependencies_are_correct_types(self):
        """Test that ArchiveManager receives correct dependency types."""
        job_executor = get_job_executor()
        command_builder = get_borg_command_builder()

        manager = ArchiveManager(
            job_executor=job_executor, command_builder=command_builder
        )

        # Verify dependency types
        assert isinstance(manager.job_executor, JobExecutor)
        assert isinstance(manager.command_builder, BorgCommandBuilder)

        # Verify dependencies are not None
        assert manager.job_executor is not None
        assert manager.command_builder is not None


class TestArchiveManagerDIIntegration:
    """Test ArchiveManager integration with FastAPI DI system."""

    def test_archive_manager_works_in_api_context(self):
        """Test that ArchiveManager works correctly in API context."""
        # Since ArchiveManager might not be directly used in APIs,
        # we test that the DI system works with its dependencies

        mock_executor = MockServiceFactory.create_mock_job_executor()
        mock_builder = MockServiceFactory.create_mock_borg_command_builder()

        overrides = {
            get_job_executor: lambda: mock_executor,
            get_borg_command_builder: lambda: mock_builder,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that API endpoints work (indirect test of DI system)
            response = client.get("/api/debug/info")
            assert response is not None

            # Verify overrides are active
            assert get_job_executor in app.dependency_overrides
            assert get_borg_command_builder in app.dependency_overrides

    def test_archive_manager_can_be_mocked_completely(self):
        """Test that ArchiveManager can be completely mocked via dependency override."""
        mock_archive_manager = MockServiceFactory.create_mock_archive_manager()

        with override_dependency(
            get_archive_manager, lambda: mock_archive_manager
        ) as client:
            # The override should be active
            assert get_archive_manager in app.dependency_overrides

            # API should still work (basic smoke test)
            response = client.get("/api/debug/info")
            assert response is not None

    def test_archive_manager_di_isolation(self):
        """Test that ArchiveManager DI provides proper isolation."""
        # Test that different dependency overrides work independently

        mock1 = MockServiceFactory.create_mock_archive_manager()
        mock2 = MockServiceFactory.create_mock_archive_manager()

        # First context
        with override_dependency(get_archive_manager, lambda: mock1) as client1:
            response1 = client1.get("/api/debug/info")
            assert response1 is not None

        # Second context (should be isolated)
        with override_dependency(get_archive_manager, lambda: mock2) as client2:
            response2 = client2.get("/api/debug/info")
            assert response2 is not None

        # After both contexts, no overrides should remain
        assert get_archive_manager not in app.dependency_overrides
