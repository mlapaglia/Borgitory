"""
Tests for the FastAPI Dependency Injection Testing Infrastructure

This module validates that our DI testing utilities work correctly before we use them
for the hybrid service migration.
"""

import pytest
from unittest.mock import Mock

from tests.utils.di_testing import (
    override_dependency,
    override_multiple_dependencies,
    MockServiceFactory,
    DependencyTestHelper,
)
from borgitory.dependencies import (
    get_debug_service,
    get_borg_service,
)
from borgitory.main import app


class TestDependencyOverrideInfrastructure:
    """Test that our dependency override infrastructure works correctly."""

    def test_single_dependency_override(self) -> None:
        """Test that single dependency override works."""
        mock_debug_service = MockServiceFactory.create_mock_debug_service()

        with override_dependency(
            get_debug_service, lambda: mock_debug_service
        ) as client:
            # Verify the override is active
            assert app.dependency_overrides[get_debug_service] is not None

            # Test that we can make requests (basic smoke test)
            response = client.get("/api/debug/info")
            assert response is not None

        # Verify override is cleaned up
        assert get_debug_service not in app.dependency_overrides

    def test_multiple_dependency_overrides(self) -> None:
        """Test that multiple dependency overrides work."""
        overrides = {
            get_debug_service: lambda: MockServiceFactory.create_mock_debug_service(),
            get_borg_service: lambda: MockServiceFactory.create_mock_borg_service(),
        }

        with override_multiple_dependencies(overrides) as client:
            # Verify both overrides are active
            assert get_debug_service in app.dependency_overrides
            assert get_borg_service in app.dependency_overrides

            # Test that we can make requests
            response = client.get("/api/debug/info")
            assert response is not None

        # Verify overrides are cleaned up
        assert get_debug_service not in app.dependency_overrides
        assert get_borg_service not in app.dependency_overrides

    def test_dependency_override_isolation(self) -> None:
        """Test that dependency overrides don't interfere with each other."""
        mock1 = MockServiceFactory.create_mock_debug_service()
        mock2 = MockServiceFactory.create_mock_debug_service()

        # First override
        with override_dependency(get_debug_service, lambda: mock1):
            assert app.dependency_overrides[get_debug_service] is not None

        # Second override (should not interfere with first)
        with override_dependency(get_debug_service, lambda: mock2):
            assert app.dependency_overrides[get_debug_service] is not None

        # Both should be cleaned up
        assert get_debug_service not in app.dependency_overrides


class TestMockServiceFactory:
    """Test that our mock service factory creates proper mocks."""

    def test_create_mock_borg_service(self) -> None:
        """Test BorgService mock creation."""
        mock = MockServiceFactory.create_mock_borg_service()

        # Verify it's a proper mock with the right spec
        assert isinstance(mock, Mock)
        assert hasattr(mock, "list_archives")
        assert hasattr(mock, "verify_repository_access")

        # Verify default return values are set
        assert mock.list_archives.return_value == []
        assert mock.verify_repository_access.return_value is True

    def test_create_mock_debug_service(self) -> None:
        """Test DebugService mock creation."""
        mock = MockServiceFactory.create_mock_debug_service()

        assert isinstance(mock, Mock)
        assert hasattr(mock, "get_debug_info")

        # Verify default return value structure matches our DebugInfo TypedDict
        debug_info = mock.get_debug_info.return_value
        assert "system" in debug_info
        assert "application" in debug_info
        assert "database" in debug_info
        assert "volumes" in debug_info
        assert "tools" in debug_info
        assert "environment" in debug_info
        assert "job_manager" in debug_info

    def test_create_mock_job_stream_service(self) -> None:
        """Test JobStreamService mock creation."""
        mock = MockServiceFactory.create_mock_job_stream_service()

        assert isinstance(mock, Mock)
        assert hasattr(mock, "stream_all_jobs")
        assert hasattr(mock, "stream_job_output")
        assert hasattr(mock, "get_current_jobs_data")

        # Verify streaming methods are set up
        assert mock.get_current_jobs_data.return_value == []

    def test_create_mock_job_render_service(self) -> None:
        """Test JobRenderService mock creation."""
        mock = MockServiceFactory.create_mock_job_render_service()

        assert isinstance(mock, Mock)
        assert hasattr(mock, "render_jobs_html")
        assert hasattr(mock, "render_current_jobs_html")
        assert hasattr(mock, "get_job_display_data")
        assert hasattr(mock, "get_job_for_template")
        assert hasattr(mock, "_render_job_html")

        # Verify HTML return values
        assert "Mock jobs HTML" in mock.render_jobs_html.return_value
        assert "Mock current jobs HTML" in mock.render_current_jobs_html.return_value

    def test_create_mock_archive_manager(self) -> None:
        """Test ArchiveManager mock creation."""
        mock = MockServiceFactory.create_mock_archive_manager()

        assert isinstance(mock, Mock)
        assert hasattr(mock, "get_archive_metadata")
        assert hasattr(mock, "validate_archive_path")

        # Verify return values
        assert mock.validate_archive_path.return_value is True

    def test_create_mock_repository_service(self) -> None:
        """Test RepositoryService mock creation."""
        mock = MockServiceFactory.create_mock_repository_service()

        assert isinstance(mock, Mock)
        assert hasattr(mock, "scan_repositories")
        assert hasattr(mock, "create_repository")
        assert hasattr(mock, "delete_repository")

        # Verify return values
        assert mock.scan_repositories.return_value == []
        assert mock.delete_repository.return_value is True


class TestDependencyTestHelper:
    """Test the dependency testing helper utilities."""

    def test_verify_service_creation(self) -> None:
        """Test service creation verification."""
        # Test with working service factory
        service = DependencyTestHelper.verify_service_creation(get_debug_service)
        assert service is not None

    def test_verify_service_creation_failure(self) -> None:
        """Test service creation verification with failing factory."""

        def failing_factory():
            raise RuntimeError("Service creation failed")

        with pytest.raises(AssertionError, match="Service creation failed"):
            DependencyTestHelper.verify_service_creation(failing_factory)

    def test_verify_dependency_override_works(self) -> None:
        """Test dependency override verification."""
        mock_debug_service = MockServiceFactory.create_mock_debug_service()

        # This should not raise any exceptions
        DependencyTestHelper.verify_dependency_override_works(
            get_debug_service, mock_debug_service, "/api/debug/info"
        )


class TestIntegrationWithExistingTests:
    """Test integration with existing test patterns."""

    def test_can_still_call_services_directly(self) -> None:
        """Test that we can still call services directly (current pattern)."""
        # This tests backward compatibility during migration
        service = get_debug_service()
        assert service is not None

        # Verify it's the actual service, not a mock
        from borgitory.services.debug_service import DebugService

        assert isinstance(service, DebugService)

    def test_direct_calls_vs_dependency_overrides(self) -> None:
        """Test FastAPI DI behavior - direct calls create new instances, overrides work in FastAPI context."""

        # With FastAPI DI, direct calls create new instances each time
        service1 = get_debug_service()
        service2 = get_debug_service()
        assert service1 is not service2  # No longer singleton

        # Override works in FastAPI context
        mock_service = MockServiceFactory.create_mock_debug_service()
        with override_dependency(get_debug_service, lambda: mock_service) as client:
            # Test that API uses the mock
            response = client.get("/api/debug/info")
            assert response.status_code == 200

            # Verify the mock was called
            assert mock_service.get_debug_info.called
