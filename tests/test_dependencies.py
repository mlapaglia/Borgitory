"""
Tests for FastAPI dependency providers
"""

import inspect
from unittest.mock import Mock, AsyncMock

from borgitory.dependencies import (
    get_simple_command_runner,
    get_borg_service,
    get_job_service,
    get_recovery_service,
    get_job_stream_service,
    get_job_render_service,
    get_debug_service,
    get_rclone_service,
    get_repository_stats_service,
    get_volume_service,
    get_job_manager_dependency,
)
from tests.utils.di_testing import (
    override_dependency,
    override_multiple_dependencies,
)
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.borg_service import BorgService
from borgitory.services.jobs.job_service import JobService
from borgitory.services.recovery_service import RecoveryService
from borgitory.services.notifications.service import NotificationService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.debug_service import DebugService
from borgitory.services.rclone_service import RcloneService
from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
)
from borgitory.services.volumes.volume_service import VolumeService


class TestDependencies:
    """Test class for dependency providers."""

    def test_get_simple_command_runner(self) -> None:
        """Test SimpleCommandRunner dependency provider."""
        runner = get_simple_command_runner()

        assert isinstance(runner, SimpleCommandRunner)
        assert runner.timeout == 300  # Default timeout

        # Should return same instance due to singleton pattern
        runner2 = get_simple_command_runner()
        assert runner is runner2

    def test_get_borg_service(self) -> None:
        """Test BorgService dependency provider with FastAPI DI."""
        # Test that BorgService works in FastAPI context
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.scan_for_repositories.return_value = []

        with override_dependency(get_borg_service, lambda: mock_borg_service) as client:
            response = client.get("/api/repositories/scan")
            assert response.status_code == 200

            # Verify our mock was used
            assert mock_borg_service.scan_for_repositories.called

        # Test that DI creates new instances (no longer singleton)
        # Note: Direct calls receive Depends objects, so we test the DI behavior
        sig = inspect.signature(get_borg_service)
        assert "command_runner" in sig.parameters
        assert "volume_service" in sig.parameters
        assert "job_manager" in sig.parameters

    def test_borg_service_has_injected_command_runner(self) -> None:
        """Test that BorgService receives the proper command runner dependency via FastAPI DI."""
        # Create mock dependencies
        mock_command_runner = Mock()
        mock_volume_service = Mock()
        mock_job_manager = Mock()

        # Set up mock return values (need async mocks for async methods)
        mock_command_runner.run_command = AsyncMock(
            return_value=Mock(success=True, stdout="", stderr="")
        )
        mock_volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/test/volume"]
        )

        # Override dependencies
        overrides = {
            get_simple_command_runner: lambda: mock_command_runner,
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that the repository scan endpoint works with our mocked dependencies
            response = client.get("/api/repositories/scan")
            assert response.status_code == 200

            # The mock command runner should have been used
            assert mock_command_runner.run_command.called

    def test_borg_service_has_injected_volume_service(self) -> None:
        """Test that BorgService receives the proper volume service dependency via FastAPI DI."""
        # Create mock dependencies
        mock_command_runner = Mock()
        mock_volume_service = Mock()
        mock_job_manager = Mock()

        # Set up mock return values (BorgService calls get_mounted_volumes on volume_service)
        mock_volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/test/volume"]
        )

        # Override dependencies
        overrides = {
            get_simple_command_runner: lambda: mock_command_runner,
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that the repository scan endpoint works with our mocked dependencies
            response = client.get("/api/repositories/scan")
            assert response.status_code == 200

            # The mock volume service should have been used
            assert mock_volume_service.get_mounted_volumes.called

    def test_dependency_isolation_in_tests(self) -> None:
        """Test that dependencies can be properly mocked in tests."""

        # This demonstrates how to inject mock dependencies for testing
        mock_runner = Mock(spec=SimpleCommandRunner)
        service = BorgService(command_runner=mock_runner)

        assert service.command_runner is mock_runner
        assert isinstance(mock_runner, Mock)

    def test_get_job_service(self) -> None:
        """Test JobService dependency provider."""
        service = get_job_service()

        assert isinstance(service, JobService)

        # JobService creates new instances per request (not singleton)
        service2 = get_job_service()
        assert service is not service2  # Different instances
        assert isinstance(service2, JobService)

    def test_get_recovery_service(self) -> None:
        """Test RecoveryService dependency provider."""
        service = get_recovery_service()

        assert isinstance(service, RecoveryService)

        # Should return same instance due to singleton pattern
        service2 = get_recovery_service()
        assert service is service2

    def test_get_notification_service(self) -> None:
        """Test NotificationService dependency provider."""
        # Import the singleton version for direct testing
        from borgitory.dependencies import get_notification_service_singleton

        service = get_notification_service_singleton()

        assert isinstance(service, NotificationService)

        # Should return same instance due to singleton pattern
        service2 = get_notification_service_singleton()
        assert service is service2

    def test_get_job_stream_service(self) -> None:
        """Test JobStreamService dependency provider."""
        service = get_job_stream_service()

        assert isinstance(service, JobStreamService)

        # No longer singleton - FastAPI DI creates new instances
        service2 = get_job_stream_service()
        assert service is not service2, "JobStreamService should no longer be singleton"

    def test_get_job_render_service(self) -> None:
        """Test JobRenderService dependency provider."""
        service = get_job_render_service()

        assert isinstance(service, JobRenderService)

        # No longer singleton - FastAPI DI creates new instances
        service2 = get_job_render_service()
        assert service is not service2, "JobRenderService should no longer be singleton"

    def test_get_debug_service(self) -> None:
        """Test DebugService dependency provider with FastAPI DI."""

        # Test that DebugService works in FastAPI context
        mock_debug_service = Mock(spec=DebugService)
        # Mock data that matches our DebugInfo TypedDict structure
        mock_debug_info = {
            "system": {
                "platform": "Test Platform",
                "system": "TestOS",
                "release": "1.0",
                "version": "1.0.0",
                "architecture": "x64",
                "processor": "Test Processor",
                "hostname": "test-host",
                "python_version": "Python 3.9.0",
                "python_executable": "/usr/bin/python",
            },
            "application": {
                "borgitory_version": "1.0.0",
                "debug_mode": False,
                "startup_time": "2023-01-01T12:00:00",
                "working_directory": "/test/dir",
            },
            "database": {
                "repository_count": 5,
                "total_jobs": 100,
                "jobs_today": 10,
                "database_type": "SQLite",
                "database_url": "sqlite:///test.db",
                "database_size": "1.0 MB",
                "database_size_bytes": 1048576,
                "database_accessible": True,
            },
            "volumes": {
                "mounted_volumes": ["/data", "/backup"],
                "total_mounted_volumes": 2,
            },
            "tools": {
                "borg": {"version": "borg 1.2.0", "accessible": True},
                "rclone": {"version": "rclone v1.58.0", "accessible": True},
            },
            "environment": {
                "PATH": "/usr/bin:/bin",
                "HOME": "/home/user",
                "DEBUG": "false",
            },
            "job_manager": {
                "active_jobs": 2,
                "total_jobs": 5,
                "job_manager_running": True,
            },
        }
        mock_debug_service.get_debug_info.return_value = mock_debug_info

        with override_dependency(
            get_debug_service, lambda: mock_debug_service
        ) as client:
            response = client.get("/api/debug/info")
            assert response.status_code == 200

            # Verify our mock was used
            assert mock_debug_service.get_debug_info.called

        # Test that DI creates new instances (no longer singleton)
        # Note: Direct calls receive Depends objects, so we test the DI behavior
        import inspect

        sig = inspect.signature(get_debug_service)
        assert "volume_service" in sig.parameters
        assert "job_manager" in sig.parameters

    def test_debug_service_has_injected_volume_service(self) -> None:
        """Test that DebugService receives the proper volume service dependency via FastAPI DI."""

        # Create mock dependencies
        mock_volume_service = Mock()
        mock_job_manager = Mock()

        # Set up mock return values (DebugService calls get_volume_info, not get_mounted_volumes)
        mock_volume_service.get_volume_info = AsyncMock(
            return_value={
                "mounted_volumes": ["/test/volume"],
                "total_mounted_volumes": 1,
                "accessible": True,
            }
        )

        # Override dependencies
        overrides = {
            get_volume_service: lambda: mock_volume_service,
            get_job_manager_dependency: lambda: mock_job_manager,
        }

        with override_multiple_dependencies(overrides) as client:
            # Test that the debug service endpoint works with our mocked dependencies
            response = client.get("/api/debug/info")
            assert response.status_code == 200

            # Verify that our mocked volume service was used
            debug_info = response.json()
            assert "volumes" in debug_info

            # The mock volume service should have been called
            assert mock_volume_service.get_volume_info.called

    def test_get_rclone_service(self) -> None:
        """Test RcloneService dependency provider."""
        service = get_rclone_service()

        assert isinstance(service, RcloneService)

        # Should return same instance due to singleton pattern
        service2 = get_rclone_service()
        assert service is service2

    def test_get_repository_stats_service(self) -> None:
        """Test RepositoryStatsService dependency provider."""
        service = get_repository_stats_service()

        assert isinstance(service, RepositoryStatsService)

        # Should return same instance due to singleton pattern
        service2 = get_repository_stats_service()
        assert service is service2

    def test_get_volume_service(self) -> None:
        """Test VolumeService dependency provider."""
        service = get_volume_service()

        assert isinstance(service, VolumeService)

        # Should return same instance due to singleton pattern
        service2 = get_volume_service()
        assert service is service2
