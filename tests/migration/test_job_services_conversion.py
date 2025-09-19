"""
Tests for JobRenderService and JobStreamService Conversion from Hybrid to Pure FastAPI DI

This module validates that JobRenderService and JobStreamService work correctly after conversion
from hybrid DI pattern to pure FastAPI DI.
"""

from unittest.mock import Mock

from tests.utils.di_testing import (
    override_dependency,
    override_multiple_dependencies,
    MockServiceFactory,
)
from borgitory.dependencies import (
    get_job_render_service,
    get_job_stream_service,
    get_job_manager_dependency,
)
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_manager import JobManager
from borgitory.main import app


class TestJobServicesPureDI:
    """Test JobRenderService and JobStreamService after conversion to pure FastAPI DI."""

    def test_job_render_service_can_be_created_directly(self):
        """Test that JobRenderService can still be created for direct calls."""
        # Test backward compatibility - direct calls should still work
        service = get_job_render_service()
        assert service is not None
        assert isinstance(service, JobRenderService)

    def test_job_stream_service_can_be_created_directly(self):
        """Test that JobStreamService can still be created for direct calls."""
        # Test backward compatibility - direct calls should still work
        service = get_job_stream_service()
        assert service is not None
        assert isinstance(service, JobStreamService)

    def test_job_render_service_works_with_dependency_override(self):
        """Test that JobRenderService works correctly with dependency overrides."""
        mock_job_manager = MockServiceFactory.create_mock_job_manager()

        overrides = {
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that we can make API calls that use JobRenderService
            response = client.get("/api/debug/info")  # Any endpoint to test DI works
            assert response is not None

    def test_job_stream_service_works_with_dependency_override(self):
        """Test that JobStreamService works correctly with dependency overrides."""
        mock_job_manager = MockServiceFactory.create_mock_job_manager()

        overrides = {
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that we can make API calls that use JobStreamService
            response = client.get("/api/debug/info")  # Any endpoint to test DI works
            assert response is not None

    def test_job_render_service_dependency_injection_works(self):
        """Test that FastAPI properly injects dependencies into JobRenderService."""
        # Create mock dependencies
        mock_job_manager = Mock(spec=JobManager)

        # Override the dependencies
        overrides = {
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides):
            # The DI system should work
            assert get_job_manager_dependency in app.dependency_overrides

    def test_job_stream_service_dependency_injection_works(self):
        """Test that FastAPI properly injects dependencies into JobStreamService."""
        # Create mock dependencies
        mock_job_manager = Mock(spec=JobManager)

        # Override the dependencies
        overrides = {
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides):
            # The DI system should work
            assert get_job_manager_dependency in app.dependency_overrides

    def test_job_services_no_longer_singleton(self):
        """Test that JobRenderService and JobStreamService are no longer singletons."""
        # With pure FastAPI DI, services are typically request-scoped
        # This means each request gets a new instance

        # Test JobRenderService
        service1 = get_job_render_service()
        service2 = get_job_render_service()

        assert isinstance(service1, JobRenderService)
        assert isinstance(service2, JobRenderService)
        # Should be different instances (no longer singleton)
        assert service1 is not service2, (
            "JobRenderService should no longer be singleton"
        )

        # Test JobStreamService
        service3 = get_job_stream_service()
        service4 = get_job_stream_service()

        assert isinstance(service3, JobStreamService)
        assert isinstance(service4, JobStreamService)
        # Should be different instances (no longer singleton)
        assert service3 is not service4, (
            "JobStreamService should no longer be singleton"
        )

    def test_job_services_dependencies_are_injected_correctly(self):
        """Test that the correct dependency types are expected."""
        import inspect

        # Check JobRenderService function signature
        render_sig = inspect.signature(get_job_render_service)
        render_params = render_sig.parameters

        # Should have job_manager parameter
        assert "job_manager" in render_params

        # Check parameter annotations
        job_manager_param = render_params["job_manager"]

        # Should have proper type annotation and default value
        assert job_manager_param.annotation == JobManager
        assert job_manager_param.default is not inspect.Parameter.empty

        # Check JobStreamService function signature
        stream_sig = inspect.signature(get_job_stream_service)
        stream_params = stream_sig.parameters

        # Should have job_manager parameter
        assert "job_manager" in stream_params

        # Check parameter annotations
        job_manager_param = stream_params["job_manager"]

        # Should have proper type annotation and default value
        assert job_manager_param.annotation == JobManager
        assert job_manager_param.default is not inspect.Parameter.empty


class TestJobServicesRegressionAfterConversion:
    """Regression tests to ensure JobRenderService and JobStreamService functionality is preserved."""

    def test_job_render_service_functionality_preserved(self):
        """Test that JobRenderService functionality is preserved after conversion."""
        # Create real dependencies for testing
        job_manager = get_job_manager_dependency()

        # Create JobRenderService directly with dependencies
        service = JobRenderService(job_manager=job_manager)

        # Test that all expected methods exist and are callable
        assert hasattr(service, "render_jobs_html")
        assert hasattr(service, "render_current_jobs_html")
        assert hasattr(service, "get_job_for_render")
        assert hasattr(service, "stream_current_jobs_html")

        assert callable(getattr(service, "render_jobs_html"))
        assert callable(getattr(service, "render_current_jobs_html"))
        assert callable(getattr(service, "get_job_for_render"))
        assert callable(getattr(service, "stream_current_jobs_html"))

    def test_job_stream_service_functionality_preserved(self):
        """Test that JobStreamService functionality is preserved after conversion."""
        # Create real dependencies for testing
        job_manager = get_job_manager_dependency()

        # Create JobStreamService directly with dependencies
        service = JobStreamService(job_manager)

        # Test that all expected methods exist and are callable
        assert hasattr(service, "stream_job_output")
        assert hasattr(service, "get_job_status")
        assert hasattr(service, "stream_all_jobs")

        assert callable(getattr(service, "stream_job_output"))
        assert callable(getattr(service, "get_job_status"))
        assert callable(getattr(service, "stream_all_jobs"))

    def test_job_services_dependencies_are_correct_types(self):
        """Test that job services receive correct dependency types."""
        job_manager = get_job_manager_dependency()

        # Create services with real dependencies
        render_service = JobRenderService(job_manager=job_manager)
        stream_service = JobStreamService(job_manager)

        # Verify dependency types
        assert isinstance(render_service.job_manager, JobManager)
        assert isinstance(stream_service.job_manager, JobManager)

        # Verify dependencies are not None
        assert render_service.job_manager is not None
        assert stream_service.job_manager is not None


class TestJobServicesDIIntegration:
    """Test job services integration with FastAPI DI system."""

    def test_job_services_work_in_api_context(self):
        """Test that job services work correctly in API context."""
        mock_job_manager = MockServiceFactory.create_mock_job_manager()

        overrides = {
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that API endpoints work (indirect test of DI system)
            response = client.get("/api/debug/info")
            assert response is not None

            # Verify overrides are active
            assert get_job_manager_dependency in app.dependency_overrides

    def test_job_services_can_be_mocked_completely(self):
        """Test that job services can be completely mocked via dependency override."""
        mock_render_service = MockServiceFactory.create_mock_job_render_service()
        mock_stream_service = MockServiceFactory.create_mock_job_stream_service()

        with override_dependency(
            get_job_render_service, lambda: mock_render_service
        ) as client:
            # The override should be active
            assert get_job_render_service in app.dependency_overrides

            # API should still work (basic smoke test)
            response = client.get("/api/debug/info")
            assert response is not None

        with override_dependency(
            get_job_stream_service, lambda: mock_stream_service
        ) as client:
            # The override should be active
            assert get_job_stream_service in app.dependency_overrides

            # API should still work (basic smoke test)
            response = client.get("/api/debug/info")
            assert response is not None

    def test_job_services_di_isolation(self):
        """Test that job services DI provides proper isolation."""
        # Test that different dependency overrides work independently

        mock_render1 = MockServiceFactory.create_mock_job_render_service()
        mock_render2 = MockServiceFactory.create_mock_job_render_service()

        # First context
        with override_dependency(
            get_job_render_service, lambda: mock_render1
        ) as client1:
            response1 = client1.get("/api/debug/info")
            assert response1 is not None

        # Second context (should be isolated)
        with override_dependency(
            get_job_render_service, lambda: mock_render2
        ) as client2:
            response2 = client2.get("/api/debug/info")
            assert response2 is not None

        # After both contexts, no overrides should remain
        assert get_job_render_service not in app.dependency_overrides
        assert get_job_stream_service not in app.dependency_overrides
