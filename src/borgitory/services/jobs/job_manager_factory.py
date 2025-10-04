"""
Job Manager Factory - Factory pattern for creating job manager instances with proper dependency injection
"""

from typing import Optional, Callable, Any
from borgitory.services.jobs.job_models import JobManagerConfig, JobManagerDependencies


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
            custom_dependencies = JobManagerDependencies()

        # Create core services with proper configuration
        deps = JobManagerDependencies(
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

        # Job Executor
        if custom_dependencies.job_executor:
            deps.job_executor = custom_dependencies.job_executor
        else:
            # Create command executor for JobExecutor
            from borgitory.services.command_execution.command_executor_factory import (
                create_command_executor,
            )
            from borgitory.services.jobs.job_executor import JobExecutor

            command_executor = create_command_executor()
            deps.job_executor = JobExecutor(command_executor)

        # Job Output Manager
        if custom_dependencies.output_manager:
            deps.output_manager = custom_dependencies.output_manager
        else:
            from borgitory.services.jobs.job_output_manager import JobOutputManager

            deps.output_manager = JobOutputManager(
                max_lines_per_job=config.max_output_lines_per_job
            )

        # Job Queue Manager
        if custom_dependencies.queue_manager:
            deps.queue_manager = custom_dependencies.queue_manager
        else:
            from borgitory.services.jobs.job_queue_manager import JobQueueManager

            deps.queue_manager = JobQueueManager(
                max_concurrent_backups=config.max_concurrent_backups,
                max_concurrent_operations=config.max_concurrent_operations,
                queue_poll_interval=config.queue_poll_interval,
            )

        # Job Event Broadcaster
        if custom_dependencies.event_broadcaster:
            deps.event_broadcaster = custom_dependencies.event_broadcaster
        else:
            from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
                JobEventBroadcaster,
            )

            deps.event_broadcaster = JobEventBroadcaster(
                max_queue_size=config.sse_max_queue_size,
                keepalive_timeout=config.sse_keepalive_timeout,
            )

        if custom_dependencies.database_manager:
            deps.database_manager = custom_dependencies.database_manager
        else:
            from borgitory.services.jobs.job_database_manager import JobDatabaseManager

            deps.database_manager = JobDatabaseManager(
                db_session_factory=deps.db_session_factory,
            )

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

        complete_deps = JobManagerDependencies(
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
        mock_subprocess: Optional[Callable[..., Any]] = None,
        mock_db_session: Optional[Callable[[], Any]] = None,
        mock_rclone_service: Optional[Any] = None,
        mock_http_client: Optional[Callable[[], Any]] = None,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create dependencies with mocked services for testing"""

        test_deps = JobManagerDependencies(
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
    mock_subprocess: Optional[Callable[..., Any]] = None,
    mock_db_session: Optional[Callable[[], Any]] = None,
    mock_rclone_service: Optional[Any] = None,
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_subprocess=mock_subprocess,
        mock_db_session=mock_db_session,
        mock_rclone_service=mock_rclone_service,
    )
