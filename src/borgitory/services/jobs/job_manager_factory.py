"""
Job Manager Factory - Factory pattern for creating job manager instances with proper dependency injection
"""

from typing import Optional, Callable, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from borgitory.models.database import async_session_maker
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
from borgitory.services.path.platform_service import PlatformService
from borgitory.services.rclone_service import RcloneService


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

            # Create all required core services
            event_broadcaster = JobEventBroadcaster(
                max_queue_size=config.sse_max_queue_size,
                keepalive_timeout=config.sse_keepalive_timeout,
            )

            platform_service = PlatformService()
            command_executor = create_command_executor(platform_service)
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
                async_session_maker=async_session_maker,
            )

            # For basic dependencies, we need to provide all required services
            # Import the required services
            from borgitory.dependencies import (
                get_rclone_service,
                get_file_service,
                get_encryption_service,
                get_storage_factory,
                get_registry_factory,
                get_provider_registry,
                get_hook_execution_service,
                get_notification_service_singleton,
            )
            from borgitory.services.notifications.providers.discord_provider import (
                HttpClient,
            )

            file_service = get_file_service(command_executor, platform_service)
            rclone_service = get_rclone_service(command_executor, file_service)

            custom_dependencies = JobManagerDependencies(
                event_broadcaster=event_broadcaster,
                job_executor=job_executor,
                output_manager=output_manager,
                queue_manager=queue_manager,
                database_manager=database_manager,
                async_session_maker=async_session_maker,
                rclone_service=rclone_service,
                http_client_factory=lambda: HttpClient(),  # type: ignore
                encryption_service=get_encryption_service(),
                storage_factory=get_storage_factory(rclone_service),
                provider_registry=get_provider_registry(
                    registry_factory=get_registry_factory()
                ),
                notification_service=get_notification_service_singleton(),
                hook_execution_service=get_hook_execution_service(),
            )

        # Create core services with proper configuration
        deps = JobManagerDependencies(
            event_broadcaster=custom_dependencies.event_broadcaster,
            job_executor=custom_dependencies.job_executor,
            output_manager=custom_dependencies.output_manager,
            queue_manager=custom_dependencies.queue_manager,
            database_manager=custom_dependencies.database_manager,
            async_session_maker=custom_dependencies.async_session_maker,
            rclone_service=custom_dependencies.rclone_service,
            http_client_factory=custom_dependencies.http_client_factory,
            encryption_service=custom_dependencies.encryption_service,
            storage_factory=custom_dependencies.storage_factory,
            provider_registry=custom_dependencies.provider_registry,
            notification_service=custom_dependencies.notification_service,
            hook_execution_service=custom_dependencies.hook_execution_service,
            # Use provided dependencies or create new ones
            subprocess_executor=custom_dependencies.subprocess_executor,
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
            get_file_service,
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

        platform_service = PlatformService()
        command_executor = create_command_executor(platform_service)
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
            async_session_maker=async_session_maker,
        )

        from borgitory.services.notifications.providers.discord_provider import (
            HttpClient,
        )

        file_service = get_file_service(command_executor, platform_service)
        rclone_service = get_rclone_service(command_executor, file_service)

        complete_deps = JobManagerDependencies(
            event_broadcaster=get_job_event_broadcaster(),
            job_executor=job_executor,
            output_manager=output_manager,
            queue_manager=queue_manager,
            database_manager=database_manager,
            async_session_maker=async_session_maker,
            rclone_service=rclone_service,
            http_client_factory=lambda: HttpClient(),  # type: ignore
            encryption_service=get_encryption_service(),
            storage_factory=get_storage_factory(rclone_service),
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
        mock_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
        mock_rclone_service: Optional[RcloneService] = None,
        mock_http_client: Optional[Callable[[], Any]] = None,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create dependencies with mocked services for testing"""

        from unittest.mock import Mock

        mock_job_executor = Mock(spec=ProcessExecutorProtocol)
        mock_output_manager = Mock(spec=JobOutputManagerProtocol)
        mock_queue_manager = Mock(spec=JobQueueManagerProtocol)
        mock_database_manager = Mock(spec=JobDatabaseManagerProtocol)
        mock_event_broadcaster = mock_event_broadcaster or Mock(
            spec=JobEventBroadcasterProtocol
        )
        session_maker_mock = mock_async_session_maker or Mock(
            spec=async_sessionmaker[AsyncSession]
        )
        rclone_mock = mock_rclone_service if mock_rclone_service is not None else Mock()

        mock_encryption_service = Mock()
        mock_storage_factory = Mock()
        mock_provider_registry = Mock()
        mock_notification_service = Mock()
        mock_hook_execution_service = Mock()
        mock_http_client_factory = mock_http_client or Mock()

        test_deps = JobManagerDependencies(
            event_broadcaster=mock_event_broadcaster,
            job_executor=mock_job_executor,
            output_manager=mock_output_manager,
            queue_manager=mock_queue_manager,
            database_manager=mock_database_manager,
            async_session_maker=session_maker_mock,
            rclone_service=rclone_mock,
            http_client_factory=mock_http_client_factory,
            encryption_service=mock_encryption_service,
            storage_factory=mock_storage_factory,
            provider_registry=mock_provider_registry,
            notification_service=mock_notification_service,
            hook_execution_service=mock_hook_execution_service,
            subprocess_executor=mock_subprocess,
        )

        return cls.create_dependencies(config=config, custom_dependencies=test_deps)


def get_default_job_manager_dependencies() -> JobManagerDependencies:
    """Get default job manager dependencies (production configuration)"""
    return JobManagerFactory.create_complete_dependencies()


def get_test_job_manager_dependencies(
    mock_event_broadcaster: JobEventBroadcasterProtocol,
    mock_subprocess: Optional[Callable[..., Any]] = None,
    mock_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    mock_rclone_service: Optional[RcloneService] = None,
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_event_broadcaster=mock_event_broadcaster,
        mock_subprocess=mock_subprocess,
        mock_async_session_maker=mock_async_session_maker,
        mock_rclone_service=mock_rclone_service,
    )
