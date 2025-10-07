"""
Job Manager Factory - Factory pattern for creating job manager instances with proper dependency injection
"""

from typing import Optional, Callable, Any
from borgitory.dependencies import get_borg_service, get_repository_service
from borgitory.services.borg_service import BorgService
from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    get_job_event_broadcaster,
)
from borgitory.services.jobs.job_models import JobManagerConfig, JobManagerDependencies
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.protocols.job_queue_manager_protocol import JobQueueManagerProtocol
from borgitory.protocols.job_database_manager_protocol import JobDatabaseManagerProtocol
from borgitory.services.repositories.repository_service import RepositoryService


class JobManagerFactory:
    """Factory for creating job manager instances with proper dependency injection"""

    @classmethod
    def create_dependencies(
        cls,
        config: Optional[JobManagerConfig] = None,
        custom_dependencies: Optional[JobManagerDependencies] = None,
    ) -> JobManagerDependencies:
        """Create a complete set of dependencies for the job manager"""

        if config is None:
            config = JobManagerConfig()

        if custom_dependencies is None:
            # Create default dependencies with all required services
            from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
                JobEventBroadcaster,
            )
            from borgitory.services.command_execution.command_executor_factory import (
                create_command_executor,
            )
            from borgitory.services.jobs.job_executor import JobExecutor
            from borgitory.services.jobs.job_output_manager import JobOutputManager
            from borgitory.services.jobs.job_queue_manager import JobQueueManager
            from borgitory.services.jobs.job_database_manager import JobDatabaseManager
            from borgitory.utils.db_session import get_db_session
            from borgitory.dependencies import get_borg_service, get_repository_service
            # Create all required core services
            event_broadcaster = JobEventBroadcaster(
                max_queue_size=config.sse_max_queue_size,
                keepalive_timeout=config.sse_keepalive_timeout,
            )

            command_executor = create_command_executor()
            job_executor = JobExecutor(command_executor)

            output_manager = JobOutputManager(
                max_lines_per_job=config.max_output_lines_per_job
            )

            queue_manager = JobQueueManager(
                max_concurrent_backups=config.max_concurrent_backups,
                max_concurrent_operations=config.max_concurrent_operations,
                queue_poll_interval=config.queue_poll_interval,
            )

            database_manager = JobDatabaseManager(
                db_session_factory=get_db_session,
            )

            custom_dependencies = JobManagerDependencies(
                borg_service=get_borg_service(),
                repository_service=get_repository_service(),
                event_broadcaster=event_broadcaster,
                job_executor=job_executor,
                output_manager=output_manager,
                queue_manager=queue_manager,
                database_manager=database_manager,
            )

        # Create core services with proper configuration
        deps = JobManagerDependencies(
            borg_service=custom_dependencies.borg_service,
            repository_service=custom_dependencies.repository_service,
            event_broadcaster=custom_dependencies.event_broadcaster,
            job_executor=custom_dependencies.job_executor,
            output_manager=custom_dependencies.output_manager,
            queue_manager=custom_dependencies.queue_manager,
            database_manager=custom_dependencies.database_manager,
            # Use provided dependencies or create new ones
            subprocess_executor=custom_dependencies.subprocess_executor,
            db_session_factory=custom_dependencies.db_session_factory,
            rclone_service=custom_dependencies.rclone_service,
            http_client_factory=custom_dependencies.http_client_factory,
            encryption_service=custom_dependencies.encryption_service,
            storage_factory=custom_dependencies.storage_factory,
            provider_registry=custom_dependencies.provider_registry,
            notification_service=custom_dependencies.notification_service,
            hook_execution_service=custom_dependencies.hook_execution_service,
        )

        # All core services are now required and handled above

        return deps

    @classmethod
    def create_complete_dependencies(
        cls,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create a complete set of dependencies with all cloud sync services for production use"""

        if config is None:
            config = JobManagerConfig()

        # Import dependencies from the DI system
        from borgitory.dependencies import (
            get_rclone_service,
            get_encryption_service,
            get_storage_factory,
            get_registry_factory,
            get_provider_registry,
            get_hook_execution_service,
        )

        # Create complete dependencies with all cloud sync and notification services
        # Import singleton dependency functions
        from borgitory.dependencies import get_notification_service_singleton

        # Create required core services for complete dependencies
        from borgitory.services.command_execution.command_executor_factory import (
            create_command_executor,
        )
        from borgitory.services.jobs.job_executor import JobExecutor
        from borgitory.services.jobs.job_output_manager import JobOutputManager
        from borgitory.services.jobs.job_queue_manager import JobQueueManager
        from borgitory.services.jobs.job_database_manager import JobDatabaseManager
        from borgitory.utils.db_session import get_db_session

        command_executor = create_command_executor()
        job_executor = JobExecutor(command_executor)

        output_manager = JobOutputManager(
            max_lines_per_job=config.max_output_lines_per_job
        )

        queue_manager = JobQueueManager(
            max_concurrent_backups=config.max_concurrent_backups,
            max_concurrent_operations=config.max_concurrent_operations,
            queue_poll_interval=config.queue_poll_interval,
        )

        database_manager = JobDatabaseManager(
            db_session_factory=get_db_session,
        )

        complete_deps = JobManagerDependencies(
            borg_service=get_borg_service(),
            repository_service=get_repository_service(),
            event_broadcaster=get_job_event_broadcaster(),
            job_executor=job_executor,
            output_manager=output_manager,
            queue_manager=queue_manager,
            database_manager=database_manager,
            rclone_service=get_rclone_service(),
            encryption_service=get_encryption_service(),
            storage_factory=get_storage_factory(get_rclone_service()),
            provider_registry=get_provider_registry(
                registry_factory=get_registry_factory()
            ),
            notification_service=get_notification_service_singleton(),
            hook_execution_service=get_hook_execution_service(),
        )

        return cls.create_dependencies(config=config, custom_dependencies=complete_deps)

    @classmethod
    def create_for_testing(
        cls,
        mock_event_broadcaster: Optional[JobEventBroadcasterProtocol] = None,
        mock_subprocess: Optional[Callable[..., Any]] = None,
        mock_db_session: Optional[Callable[[], Any]] = None,
        mock_rclone_service: Optional[Any] = None,
        mock_http_client: Optional[Callable[[], Any]] = None,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create dependencies with mocked services for testing"""

        # Create mock services for testing
        from unittest.mock import Mock

        mock_job_executor = Mock(spec=ProcessExecutorProtocol)
        mock_output_manager = Mock(spec=JobOutputManagerProtocol)
        mock_queue_manager = Mock(spec=JobQueueManagerProtocol)
        mock_database_manager = Mock(spec=JobDatabaseManagerProtocol)
        mock_borg_service = Mock(spec=BorgService)
        mock_repository_service = Mock(spec=RepositoryService)
        mock_event_broadcaster = mock_event_broadcaster or Mock(
            spec=JobEventBroadcasterProtocol
        )

        test_deps = JobManagerDependencies(
            borg_service=mock_borg_service,
            repository_service=mock_repository_service,
            event_broadcaster=mock_event_broadcaster,
            job_executor=mock_job_executor,
            output_manager=mock_output_manager,
            queue_manager=mock_queue_manager,
            database_manager=mock_database_manager,
            subprocess_executor=mock_subprocess,
            db_session_factory=mock_db_session,
            rclone_service=mock_rclone_service,
            http_client_factory=mock_http_client,
        )

        return cls.create_dependencies(config=config, custom_dependencies=test_deps)

    @classmethod
    def create_minimal(cls) -> JobManagerDependencies:
        """Create minimal dependencies (useful for testing or simple use cases)"""

        config = JobManagerConfig(
            max_concurrent_backups=1,
            max_concurrent_operations=2,
            max_output_lines_per_job=100,
            sse_max_queue_size=10,
        )

        return cls.create_complete_dependencies(config=config)


def get_default_job_manager_dependencies() -> JobManagerDependencies:
    """Get default job manager dependencies (production configuration)"""
    return JobManagerFactory.create_complete_dependencies()


def get_test_job_manager_dependencies(
    mock_event_broadcaster: JobEventBroadcasterProtocol,
    mock_subprocess: Optional[Callable[..., Any]] = None,
    mock_db_session: Optional[Callable[[], Any]] = None,
    mock_rclone_service: Optional[Any] = None,
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_event_broadcaster=mock_event_broadcaster,
        mock_subprocess=mock_subprocess,
        mock_db_session=mock_db_session,
        mock_rclone_service=mock_rclone_service,
    )
