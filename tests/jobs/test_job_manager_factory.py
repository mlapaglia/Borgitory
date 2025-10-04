"""
Tests for JobManagerFactory methods for dependency injection
"""

from unittest.mock import Mock, AsyncMock

from borgitory.services.jobs.job_models import (
    JobManagerConfig,
    JobManagerDependencies,
)
from borgitory.services.jobs.job_manager_factory import (
    JobManagerFactory,
    get_default_job_manager_dependencies,
    get_test_job_manager_dependencies,
)


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
        assert deps.db_session_factory is not None

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
        assert deps.output_manager.max_lines_per_job == 2000

    def test_create_dependencies_with_custom_dependencies(self) -> None:
        """Test creating dependencies with partial custom dependencies"""
        mock_executor = Mock()
        mock_output_manager = Mock()

        custom_deps = JobManagerDependencies(
            job_executor=mock_executor,
            output_manager=mock_output_manager,
        )

        deps = JobManagerFactory.create_dependencies(custom_dependencies=custom_deps)

        # Custom dependencies should be preserved
        assert deps.job_executor is mock_executor
        assert deps.output_manager is mock_output_manager
        # Others should be created
        assert deps.queue_manager is not None
        assert deps.event_broadcaster is not None

    def test_create_for_testing(self) -> None:
        """Test creating dependencies for testing"""
        mock_subprocess = AsyncMock()
        mock_db_session = Mock()
        mock_rclone = Mock()

        deps = JobManagerFactory.create_for_testing(
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.subprocess_executor is mock_subprocess
        assert deps.db_session_factory is mock_db_session
        assert deps.rclone_service is mock_rclone

    def test_create_minimal(self) -> None:
        """Test creating minimal dependencies"""
        deps = JobManagerFactory.create_minimal()

        assert deps is not None
        assert deps.queue_manager is not None
        assert deps.output_manager is not None
        # Should have reduced limits
        assert deps.queue_manager.max_concurrent_backups == 1
        assert deps.output_manager.max_lines_per_job == 100

    def test_dependencies_post_init(self) -> None:
        """Test JobManagerDependencies post_init method"""
        # Test with no session factory
        deps = JobManagerDependencies()
        deps.__post_init__()

        assert deps.db_session_factory is not None

        # Test with custom session factory
        custom_factory = Mock()
        deps_custom = JobManagerDependencies(db_session_factory=custom_factory)
        deps_custom.__post_init__()

        assert deps_custom.db_session_factory is custom_factory


class TestJobManagerFactoryFunctions:
    """Test module-level factory functions"""

    def test_get_default_job_manager_dependencies(self) -> None:
        """Test getting default dependencies"""
        deps = get_default_job_manager_dependencies()

        assert isinstance(deps, JobManagerDependencies)
        assert deps.job_executor is not None
        assert deps.output_manager is not None
        assert deps.queue_manager is not None

    def test_get_test_job_manager_dependencies(self) -> None:
        """Test getting test dependencies"""
        mock_subprocess = AsyncMock()
        mock_db_session = Mock()
        mock_rclone = Mock()

        deps = get_test_job_manager_dependencies(
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.subprocess_executor is mock_subprocess
        assert deps.db_session_factory is mock_db_session
        assert deps.rclone_service is mock_rclone
