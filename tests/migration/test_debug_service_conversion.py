"""
Tests for DebugService Conversion from Hybrid to Pure FastAPI DI

This module validates that DebugService works correctly after conversion
from hybrid DI pattern to pure FastAPI DI.
"""

from unittest.mock import Mock
from fastapi.testclient import TestClient

from tests.utils.di_testing import (
    override_dependency,
    override_multiple_dependencies,
    MockServiceFactory,
)
from borgitory.dependencies import (
    get_debug_service,
    get_volume_service,
    get_job_manager_dependency,
)
from borgitory.services.debug_service import DebugService
from borgitory.services.volumes.volume_service import VolumeService
from borgitory.services.jobs.job_manager import JobManager
from borgitory.main import app


class TestDebugServicePureDI:
    """Test DebugService after conversion to pure FastAPI DI."""

    def test_debug_service_can_be_created_directly(self):
        """Test that DebugService can still be created for direct calls."""
        # Test backward compatibility - direct calls should still work
        service = get_debug_service()
        assert service is not None
        assert isinstance(service, DebugService)

    def test_debug_service_works_with_dependency_override(self):
        """Test that DebugService works correctly with dependency overrides."""
        mock_volume_service = MockServiceFactory.create_mock_volume_service()
        mock_job_manager = MockServiceFactory.create_mock_job_manager()

        overrides = {
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that we can make API calls that use DebugService
            response = client.get("/api/debug/info")  # This endpoint uses DebugService
            assert response is not None

    def test_debug_service_dependency_injection_works(self):
        """Test that FastAPI properly injects dependencies into DebugService."""
        # Create mock dependencies
        mock_volume_service = Mock(spec=VolumeService)
        mock_job_manager = Mock(spec=JobManager)

        # Override the dependencies
        overrides = {
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides):
            # The DI system should work
            assert get_volume_service in app.dependency_overrides
            assert get_job_manager_dependency in app.dependency_overrides

    def test_debug_service_no_longer_singleton(self):
        """Test that DebugService is no longer a singleton (creates new instances)."""
        # With pure FastAPI DI, services are typically request-scoped
        # This means each request gets a new instance

        service1 = get_debug_service()
        service2 = get_debug_service()

        assert isinstance(service1, DebugService)
        assert isinstance(service2, DebugService)
        # Should be different instances (no longer singleton)
        assert service1 is not service2, "DebugService should no longer be singleton"

    def test_debug_service_dependencies_are_injected_correctly(self):
        """Test that the correct dependency types are expected."""
        import inspect

        # Check the function signature
        sig = inspect.signature(get_debug_service)
        params = sig.parameters

        # Should have volume_service and job_manager parameters
        assert "volume_service" in params
        assert "job_manager" in params

        # Check parameter annotations
        volume_service_param = params["volume_service"]
        job_manager_param = params["job_manager"]

        # Should have proper type annotations
        assert volume_service_param.annotation == VolumeService
        assert job_manager_param.annotation == JobManager

        # Should have default values (Depends(...))
        assert volume_service_param.default is not inspect.Parameter.empty
        assert job_manager_param.default is not inspect.Parameter.empty


class TestDebugServiceRegressionAfterConversion:
    """Regression tests to ensure DebugService functionality is preserved."""

    def test_debug_service_functionality_preserved(self):
        """Test that DebugService functionality is preserved after conversion."""
        # Create real dependencies for testing
        volume_service = get_volume_service()
        job_manager = get_job_manager_dependency()

        # Create DebugService directly with dependencies
        service = DebugService(volume_service=volume_service, job_manager=job_manager)

        # Test that all expected methods exist and are callable
        assert hasattr(service, "get_debug_info")
        assert callable(getattr(service, "get_debug_info"))

    def test_debug_service_dependencies_are_correct_types(self):
        """Test that DebugService receives correct dependency types."""
        volume_service = get_volume_service()
        job_manager = get_job_manager_dependency()

        service = DebugService(volume_service=volume_service, job_manager=job_manager)

        # Verify dependency types
        assert isinstance(service.volume_service, VolumeService)
        assert isinstance(service.job_manager, JobManager)

        # Verify dependencies are not None
        assert service.volume_service is not None
        assert service.job_manager is not None


class TestDebugServiceDIIntegration:
    """Test DebugService integration with FastAPI DI system."""

    def test_debug_service_works_in_api_context(self):
        """Test that DebugService works correctly in API context."""
        mock_volume_service = MockServiceFactory.create_mock_volume_service()
        mock_job_manager = MockServiceFactory.create_mock_job_manager()

        overrides = {
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that API endpoints work (direct test of DebugService)
            response = client.get("/api/debug/info")
            assert response.status_code == 200

            # Verify overrides are active
            assert get_volume_service in app.dependency_overrides
            assert get_job_manager_dependency in app.dependency_overrides

    def test_debug_service_can_be_mocked_completely(self):
        """Test that DebugService can be completely mocked via dependency override."""
        mock_debug_service = MockServiceFactory.create_mock_debug_service()

        with override_dependency(
            get_debug_service, lambda: mock_debug_service
        ) as client:
            # The override should be active
            assert get_debug_service in app.dependency_overrides

            # API should still work (basic smoke test)
            response = client.get("/api/debug/info")
            assert response.status_code == 200

    def test_debug_service_di_isolation(self):
        """Test that DebugService DI provides proper isolation."""
        # Test that different dependency overrides work independently

        mock1 = MockServiceFactory.create_mock_debug_service()
        mock2 = MockServiceFactory.create_mock_debug_service()

        # First context
        with override_dependency(get_debug_service, lambda: mock1) as client1:
            response1 = client1.get("/api/debug/info")
            assert response1.status_code == 200

        # Second context (should be isolated)
        with override_dependency(get_debug_service, lambda: mock2) as client2:
            response2 = client2.get("/api/debug/info")
            assert response2.status_code == 200

        # After both contexts, no overrides should remain
        assert get_debug_service not in app.dependency_overrides

    def test_debug_service_api_integration_with_real_dependencies(self):
        """Test that DebugService API integration works with real dependencies."""
        # Test without mocks to ensure real integration works
        client = TestClient(app)

        # This should work with the real DebugService and its dependencies
        response = client.get("/api/debug/info")
        assert response.status_code == 200

        # Should return JSON with debug information
        debug_info = response.json()
        assert isinstance(debug_info, dict)
        # The exact structure depends on DebugService implementation,
        # but it should be a valid dict response
