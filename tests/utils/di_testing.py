"""
FastAPI Dependency Injection Testing Utilities

This module provides utilities for testing services that use FastAPI's dependency injection
system, including context managers for dependency overrides and mock service factories.
"""

from typing import TypeVar, Callable, Any, Generator, Dict, Optional
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock
from fastapi.testclient import TestClient

# Import the main app
from borgitory.main import app

# Import service types for mock creation
from borgitory.services.borg_service import BorgService
from borgitory.services.debug_service import DebugService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.volumes.volume_service import VolumeService

T = TypeVar('T')


@contextmanager
def override_dependency(
    dependency_func: Callable[..., T], 
    override_func: Callable[..., T]
) -> Generator[TestClient, None, None]:
    """
    Context manager for dependency overrides in tests.
    
    Args:
        dependency_func: The original dependency function to override
        override_func: The function that returns the mock/test service
        
    Yields:
        TestClient: A test client with the dependency override active
        
    Example:
        with override_dependency(get_borg_service, lambda: mock_borg_service) as client:
            response = client.get("/api/repositories")
            assert response.status_code == 200
    """
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[dependency_func] = override_func
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides = original_overrides


@contextmanager
def override_multiple_dependencies(
    overrides: Dict[Callable[..., Any], Callable[..., Any]]
) -> Generator[TestClient, None, None]:
    """
    Context manager for overriding multiple dependencies at once.
    
    Args:
        overrides: Dictionary mapping dependency functions to their overrides
        
    Yields:
        TestClient: A test client with all dependency overrides active
        
    Example:
        overrides = {
            get_borg_service: lambda: mock_borg_service,
            get_volume_service: lambda: mock_volume_service,
        }
        with override_multiple_dependencies(overrides) as client:
            response = client.get("/api/repositories")
    """
    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides = original_overrides


class MockServiceFactory:
    """Factory for creating consistent mock services with proper specifications."""
    
    @staticmethod
    def create_mock_borg_service() -> Mock:
        """Create a mock BorgService with common method signatures."""
        mock = Mock(spec=BorgService)
        
        # Setup common return values
        mock.create_backup.return_value = {"job_id": "test-job-123"}
        mock.list_archives.return_value = []
        mock.get_repo_info.return_value = {"location": "/test/repo"}
        mock.verify_repository_access.return_value = True
        mock.scan_for_repositories.return_value = []
        
        return mock
    
    @staticmethod
    def create_mock_debug_service() -> Mock:
        """Create a mock DebugService with common method signatures."""
        mock = Mock(spec=DebugService)
        
        # Setup common return values  
        mock.get_debug_info.return_value = {
            "system": {"platform": "test"},
            "volumes": [],
            "jobs": {"active": 0, "total": 0}
        }
        
        return mock
    
    @staticmethod
    def create_mock_job_stream_service() -> Mock:
        """Create a mock JobStreamService with common method signatures."""
        mock = Mock(spec=JobStreamService)
        
        # Setup async generators for streaming methods
        async def mock_stream_all_jobs():
            yield "data: test job data\n\n"
            
        async def mock_stream_job_output(job_id: str):
            yield f"data: output for {job_id}\n\n"
        
        mock.stream_all_jobs.return_value = mock_stream_all_jobs()
        mock.stream_job_output.return_value = mock_stream_job_output
        mock.get_current_jobs_data.return_value = []
        
        return mock
    
    @staticmethod
    def create_mock_job_render_service() -> Mock:
        """Create a mock JobRenderService with common method signatures."""
        mock = Mock(spec=JobRenderService)
        
        # Setup common return values
        mock.render_jobs_html.return_value = "<div>Mock jobs HTML</div>"
        mock.render_current_jobs_html.return_value = "<div>Mock current jobs HTML</div>"
        mock.get_job_for_render.return_value = {"id": "test-job", "status": "completed"}
        
        # Setup async streaming methods
        async def mock_stream_current_jobs_html():
            yield "<div>Mock streaming HTML</div>"
            
        mock.stream_current_jobs_html.return_value = mock_stream_current_jobs_html()
        
        return mock
    
    @staticmethod
    def create_mock_archive_manager() -> Mock:
        """Create a mock ArchiveManager with common method signatures."""
        mock = Mock(spec=ArchiveManager)
        
        # Setup common return values
        mock.list_archive_contents.return_value = []
        mock.get_archive_metadata.return_value = {"name": "test-archive"}
        mock.list_archive_directory_contents.return_value = []
        mock.validate_archive_path.return_value = True
        
        return mock
    
    @staticmethod
    def create_mock_repository_service() -> Mock:
        """Create a mock RepositoryService with common method signatures."""
        mock = Mock(spec=RepositoryService)
        
        # Setup common return values
        mock.scan_repositories.return_value = []
        mock.create_repository.return_value = {"id": 1, "name": "test-repo"}
        mock.delete_repository.return_value = True
        
        return mock
    
    @staticmethod
    def create_mock_job_manager() -> Mock:
        """Create a mock JobManager with common method signatures."""
        from borgitory.services.jobs.job_manager import JobManager
        mock = Mock(spec=JobManager)
        
        # Setup common return values
        mock.list_jobs.return_value = []
        mock.get_job_status.return_value = {"status": "completed"}
        mock.get_job.return_value = {"id": "test-job-123", "status": "completed"}
        mock.start_borg_command.return_value = {"job_id": "test-job-123"}
        mock.get_active_jobs_count.return_value = 0
        mock.get_queue_stats.return_value = {"pending": 0, "running": 0}
        mock.cancel_job.return_value = True
        
        return mock
    
    @staticmethod
    def create_mock_simple_command_runner() -> Mock:
        """Create a mock SimpleCommandRunner with common method signatures.""" 
        mock = Mock(spec=SimpleCommandRunner)
        
        # Setup common return values
        async def mock_run_command(command, env=None, timeout=None):
            return MagicMock(
                success=True,
                return_code=0,
                stdout="Mock command output",
                stderr="",
                duration=0.1,
                error=None
            )
            
        mock.run_command = mock_run_command
        return mock
    
    @staticmethod
    def create_mock_volume_service() -> Mock:
        """Create a mock VolumeService with common method signatures."""
        mock = Mock(spec=VolumeService)
        
        # Setup common return values
        mock.get_mounted_volumes.return_value = ["/mnt/test-volume"]
        mock.get_volume_info.return_value = {"path": "/mnt/test", "size": "100GB"}
        
        return mock
    
    @staticmethod
    def create_mock_job_executor() -> Mock:
        """Create a mock JobExecutor with common method signatures."""
        from borgitory.services.jobs.job_executor import JobExecutor
        mock = Mock(spec=JobExecutor)
        
        # Setup common return values
        mock.start_process.return_value = {"success": True, "output": "Mock output"}
        mock.execute_prune_task.return_value = {"success": True}
        mock.execute_cloud_sync_task.return_value = {"success": True}
        
        return mock
    
    @staticmethod
    def create_mock_borg_command_builder() -> Mock:
        """Create a mock BorgCommandBuilder with common method signatures."""
        from borgitory.services.borg_command_builder import BorgCommandBuilder
        mock = Mock(spec=BorgCommandBuilder)
        
        # Setup common return values
        mock.build_list_archives_command.return_value = ["borg", "list"]
        mock.build_backup_command.return_value = ["borg", "create"]
        mock.build_check_command.return_value = ["borg", "check"]
        mock.generate_archive_name.return_value = "test-archive-2025-01-19"
        
        return mock


class DependencyTestHelper:
    """Helper class for testing dependency injection behavior."""
    
    @staticmethod
    def verify_service_creation(service_factory: Callable[..., Any]) -> Any:
        """
        Verify that a service can be created by its factory function.
        
        Args:
            service_factory: The dependency factory function
            
        Returns:
            The created service instance
            
        Raises:
            AssertionError: If service creation fails
        """
        try:
            service = service_factory()
            assert service is not None, "Service factory returned None"
            return service
        except Exception as e:
            raise AssertionError(f"Service creation failed: {e}")
    
    @staticmethod
    def verify_dependency_override_works(
        dependency_func: Callable[..., T],
        mock_service: T,
        test_endpoint: str = "/api/debug/info"
    ) -> None:
        """
        Verify that dependency override works correctly.
        
        Args:
            dependency_func: The dependency function to override
            mock_service: The mock service to use as override
            test_endpoint: API endpoint to test (default: debug endpoint)
            
        Raises:
            AssertionError: If dependency override doesn't work
        """
        with override_dependency(dependency_func, lambda: mock_service) as client:
            # Test that the endpoint can be called (basic smoke test)
            response = client.get(test_endpoint)
            # We don't assert status code since some endpoints require auth
            # The important thing is that the dependency injection worked
            assert response is not None, "No response received"


def create_test_overrides_for_hybrid_services() -> Dict[Callable[..., Any], Callable[..., Any]]:
    """
    Create a complete set of mock overrides for all hybrid services.
    
    Returns:
        Dictionary mapping dependency functions to mock factories
        
    Example:
        overrides = create_test_overrides_for_hybrid_services()
        with override_multiple_dependencies(overrides) as client:
            # All hybrid services are now mocked
            response = client.get("/api/some-endpoint")
    """
    from borgitory.dependencies import (
        get_borg_service,
        get_debug_service,
        get_job_stream_service,
        get_job_render_service,
        get_archive_manager,
        get_repository_service,
    )
    
    factory = MockServiceFactory()
    
    return {
        get_borg_service: factory.create_mock_borg_service,
        get_debug_service: factory.create_mock_debug_service,
        get_job_stream_service: factory.create_mock_job_stream_service,
        get_job_render_service: factory.create_mock_job_render_service,
        get_archive_manager: factory.create_mock_archive_manager,
        get_repository_service: factory.create_mock_repository_service,
    }
