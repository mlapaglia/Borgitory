"""
Tests for JobManagerFactory methods for dependency injection
"""

from unittest.mock import Mock, AsyncMock

from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.services.jobs.job_models import (
    JobManagerConfig,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory


class TestJobManagerFactory:
    """Test JobManagerFactory methods for dependency injection"""

    def test_create_dependencies_default(self) -> None:
        """Test creating default dependencies"""
        deps = JobManagerFactory.create_dependencies()

        assert deps is not None
        assert deps.job_executor is not None
        assert deps.output_manager is not None
        assert deps.queue_manager is not None
        assert deps.event_broadcaster is not None
        assert deps.database_manager is not None

        # Test that it uses default session factory
        assert deps.async_session_maker is not None

    def test_create_dependencies_with_config(self) -> None:
        """Test creating dependencies with custom config"""
        config = JobManagerConfig(
            max_concurrent_backups=10,
            max_output_lines_per_job=2000,
            queue_poll_interval=0.2,
        )

        deps = JobManagerFactory.create_dependencies(config=config)

        assert deps.queue_manager is not None
        assert deps.output_manager is not None
        assert deps.queue_manager.max_concurrent_backups == 10

    def test_create_dependencies_with_custom_dependencies(self) -> None:
        """Test creating dependencies with partial custom dependencies"""
        mock_executor = Mock()
        mock_output_manager = Mock()
        mock_event_broadcaster = Mock(spec=JobEventBroadcasterProtocol)

        # Create minimal dependencies first, then override specific ones
        deps = JobManagerFactory.create_dependencies()
        deps.event_broadcaster = mock_event_broadcaster
        deps.job_executor = mock_executor
        deps.output_manager = mock_output_manager

        # Custom dependencies should be preserved
        assert deps.job_executor is mock_executor
        assert deps.output_manager is mock_output_manager
        assert deps.event_broadcaster is mock_event_broadcaster
        # Others should be created
        assert deps.queue_manager is not None
        assert deps.database_manager is not None

    def test_create_for_testing(self) -> None:
        """Test creating dependencies for testing"""
        mock_event_broadcaster = Mock(spec=JobEventBroadcasterProtocol)
        mock_subprocess = AsyncMock()
        mock_db_session = Mock()
        mock_rclone = Mock()

        deps = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=mock_event_broadcaster,
            mock_subprocess=mock_subprocess,
            mock_async_session_maker=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.event_broadcaster is mock_event_broadcaster
        assert deps.subprocess_executor is mock_subprocess
        assert deps.async_session_maker is mock_db_session
        assert deps.rclone_service is mock_rclone

    def test_dependencies_initialization(self) -> None:
        """Test JobManagerDependencies initialization"""

        # Test with factory-created dependencies - session maker should be set
        deps = JobManagerFactory.create_dependencies()
        assert deps.async_session_maker is not None

        # Test with custom session factory - should be preserved
        custom_factory = Mock()
        deps_custom = JobManagerFactory.create_dependencies()
        deps_custom.async_session_maker = custom_factory

        assert deps_custom.async_session_maker is custom_factory
