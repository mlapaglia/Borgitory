"""
FastAPI dependency providers for the application.
"""

from typing import Annotated, TYPE_CHECKING, Optional, Callable

from borgitory.services.notifications.registry_factory import (
    NotificationRegistryFactory,
)

if TYPE_CHECKING:
    from borgitory.services.notifications.registry import NotificationProviderRegistry
    from borgitory.services.notifications.service import NotificationProviderFactory
    from borgitory.services.notifications.providers.discord_provider import HttpClient
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session
from borgitory.models.database import get_db
from borgitory.utils.template_paths import get_template_directory
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.borg_service import BorgService
from borgitory.services.jobs.job_service import JobService
from borgitory.services.backups.backup_service import BackupService
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.recovery_service import RecoveryService
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.config_service import NotificationConfigService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.debug_service import DebugService
from borgitory.services.rclone_service import RcloneService
from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
)
from borgitory.services.scheduling.scheduler_service import SchedulerService
from borgitory.services.task_definition_builder import TaskDefinitionBuilder
from borgitory.services.volumes.volume_service import VolumeService
from borgitory.services.repositories.repository_parser import RepositoryParser
from borgitory.services.borg_command_builder import BorgCommandBuilder
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
    get_job_event_broadcaster,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.configuration_service import ConfigurationService
from borgitory.services.repositories.repository_check_config_service import (
    RepositoryCheckConfigService,
)
from borgitory.services.cleanup_service import CleanupService
from borgitory.services.cron_description_service import CronDescriptionService
from borgitory.services.upcoming_backups_service import UpcomingBackupsService
from fastapi.templating import Jinja2Templates
from borgitory.services.cloud_providers import EncryptionService, StorageFactory

if TYPE_CHECKING:
    from borgitory.services.cloud_sync_service import CloudSyncService
    from borgitory.services.archives.archive_mount_manager import ArchiveMountManager
    from borgitory.protocols.command_protocols import (
        CommandRunnerProtocol,
        ProcessExecutorProtocol,
    )
    from borgitory.protocols.storage_protocols import VolumeServiceProtocol
    from borgitory.protocols.job_protocols import (
        JobManagerProtocol,
    )
    from borgitory.protocols.cloud_protocols import CloudSyncServiceProtocol
    from borgitory.factories.service_factory import CloudProviderServiceFactory
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.jobs.job_output_manager import JobOutputManager
from borgitory.services.jobs.job_queue_manager import JobQueueManager
from borgitory.services.jobs.job_database_manager import JobDatabaseManager

# Global singleton instances


# Job Manager Sub-Services (defined first to avoid forward references)
@lru_cache()
def get_job_executor() -> "ProcessExecutorProtocol":
    """
    Provide a ProcessExecutorProtocol implementation (JobExecutor).

    Request-scoped - new instance per request for proper isolation.
    Returns protocol interface for loose coupling.
    """
    return JobExecutor()


def get_job_output_manager() -> JobOutputManager:
    """
    Provide a JobOutputManager instance.

    Request-scoped for better isolation between operations.
    Configuration loaded from environment per request.
    """
    import os

    max_lines = int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000"))
    return JobOutputManager(max_lines_per_job=max_lines)


def get_job_queue_manager() -> JobQueueManager:
    """
    Provide a JobQueueManager instance.

    Request-scoped for better isolation between operations.
    Configuration loaded from environment per request.
    """
    import os

    return JobQueueManager(
        max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
        max_concurrent_operations=int(
            os.getenv("BORG_MAX_CONCURRENT_OPERATIONS", "10")
        ),
        queue_poll_interval=float(os.getenv("BORG_QUEUE_POLL_INTERVAL", "0.1")),
    )


def get_job_database_manager(
    db_session_factory: Optional[Callable[[], object]] = None,
) -> JobDatabaseManager:
    """
    Provide a JobDatabaseManager instance.

    Request-scoped for proper database session management.
    Uses default db_session_factory if none provided.
    """
    if db_session_factory is None:
        from borgitory.utils.db_session import get_db_session

        db_session_factory = get_db_session

    return JobDatabaseManager(db_session_factory=db_session_factory)


@lru_cache()
def get_simple_command_runner() -> "CommandRunnerProtocol":
    """
    Provide a CommandRunnerProtocol implementation (SimpleCommandRunner).

    Uses FastAPI's built-in caching for singleton behavior.
    Returns protocol interface for loose coupling.
    """
    return SimpleCommandRunner()


def get_backup_service(db: Session = Depends(get_db)) -> BackupService:
    """
    Provide a BackupService instance with database session.

    Pure backup execution service. Job creation is handled by JobService.
    Note: This creates a new instance per request since it depends on the database session.
    """
    return BackupService(db)


@lru_cache()
def get_recovery_service() -> RecoveryService:
    """
    Provide a RecoveryService singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return RecoveryService()


@lru_cache()
def get_notification_registry_factory() -> "NotificationRegistryFactory":
    """
    Provide a NotificationRegistryFactory singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    from borgitory.services.notifications.registry_factory import _production_factory

    return _production_factory


@lru_cache()
def get_notification_provider_registry() -> "NotificationProviderRegistry":
    """
    Provide a NotificationProviderRegistry singleton instance with proper dependency injection.

    Uses FastAPI's built-in caching for singleton behavior.
    Ensures all notification providers are registered by importing the provider modules.
    """
    factory = get_notification_registry_factory()
    return factory.create_production_registry()


@lru_cache()
def get_http_client() -> "HttpClient":
    """Provide HTTP client singleton for notification providers."""
    from borgitory.services.notifications.providers.discord_provider import (
        AiohttpClient,
    )

    return AiohttpClient()


def get_notification_provider_factory(
    http_client: "HttpClient" = Depends(get_http_client),
) -> "NotificationProviderFactory":
    """
    Provide NotificationProviderFactory with injected HTTP client.

    Following the exact pattern of cloud providers' StorageFactory.
    """
    from borgitory.services.notifications.service import NotificationProviderFactory

    return NotificationProviderFactory(http_client=http_client)


@lru_cache()
def get_notification_service_singleton() -> NotificationService:
    """
    Create NotificationService singleton for application-scoped use.

    📋 USAGE:
    ✅ Use for: Singletons, direct instantiation, tests, JobManager
    ❌ Don't use for: FastAPI endpoints (use get_notification_service instead)

    📋 PATTERN: Dual Functions
    This is the singleton version that resolves dependencies directly.
    For FastAPI DI, use get_notification_service() with Depends().

    Returns:
        NotificationService: Cached singleton instance
    """
    from borgitory.services.notifications.service import NotificationService

    http_client = get_http_client()
    provider_factory = get_notification_provider_factory(http_client)
    return NotificationService(provider_factory=provider_factory)


def get_notification_service(
    provider_factory: "NotificationProviderFactory" = Depends(
        get_notification_provider_factory
    ),
) -> NotificationService:
    """
    Provide NotificationService with FastAPI dependency injection.

    📋 USAGE:
    ✅ Use for: FastAPI endpoints with Depends(get_notification_service)
    ❌ Don't use for: Direct calls, singletons, tests

    ⚠️  WARNING: This function should ONLY be called by FastAPI's DI system.
    ⚠️  For direct calls, use get_notification_service_singleton() instead.

    📋 PATTERN: Dual Functions
    This is the FastAPI DI version that expects resolved dependencies.
    For direct calls, use get_notification_service_singleton().

    Args:
        provider_factory: Injected by FastAPI DI system

    Returns:
        NotificationService: New instance with injected dependencies

    Raises:
        RuntimeError: If called directly with Depends object
    """
    # Add runtime check to catch misuse
    if hasattr(provider_factory, "dependency"):
        raise RuntimeError(
            "get_notification_service() was called directly with a Depends object. "
            "This indicates a bug in the dependency injection setup. "
            "Use get_notification_service_singleton() for direct calls instead."
        )

    return NotificationService(provider_factory=provider_factory)


def get_notification_config_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationConfigService:
    """
    Provide a NotificationConfigService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return NotificationConfigService(db=db, notification_service=notification_service)


@lru_cache()
def get_rclone_service() -> RcloneService:
    """
    Provide a RcloneService singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return RcloneService()


@lru_cache()
def get_repository_stats_service() -> RepositoryStatsService:
    """
    Provide a RepositoryStatsService singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return RepositoryStatsService()


_scheduler_service_instance = None


def get_scheduler_service() -> SchedulerService:
    """
    Provide a SchedulerService singleton instance with proper dependency injection.

    Now uses the new DI system while maintaining backward compatibility.
    """
    global _scheduler_service_instance
    if _scheduler_service_instance is None:
        job_manager = get_job_manager_dependency()

        _scheduler_service_instance = SchedulerService(
            job_manager=job_manager, job_service_factory=None
        )
    return _scheduler_service_instance


@lru_cache()
def get_volume_service() -> "VolumeServiceProtocol":
    """
    Provide a VolumeServiceProtocol implementation (VolumeService).

    Uses FastAPI's built-in caching for singleton behavior.
    Returns protocol interface for loose coupling.
    """
    return VolumeService()


def get_task_definition_builder(db: Session = Depends(get_db)) -> TaskDefinitionBuilder:
    """
    Provide a TaskDefinitionBuilder instance with database session.

    Note: This is not cached because it needs a database session per request.
    """
    return TaskDefinitionBuilder(db)


def get_repository_parser(
    command_runner: SimpleCommandRunner = Depends(get_simple_command_runner),
) -> RepositoryParser:
    """
    Provide a RepositoryParser singleton instance with proper dependency injection.

    Uses FastAPI's dependency injection for clean separation of concerns.
    """
    return RepositoryParser(command_runner=command_runner)


@lru_cache()
def get_borg_command_builder() -> BorgCommandBuilder:
    """
    Provide a BorgCommandBuilder singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return BorgCommandBuilder()


def get_archive_manager(
    job_executor: JobExecutor = Depends(get_job_executor),
    command_builder: BorgCommandBuilder = Depends(get_borg_command_builder),
) -> ArchiveManager:
    """
    Provide an ArchiveManager instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return ArchiveManager(job_executor=job_executor, command_builder=command_builder)


def get_job_event_broadcaster_dep() -> JobEventBroadcaster:
    """
    Provide the global JobEventBroadcaster instance.

    Note: This uses the global instance to ensure all components
    share the same event broadcaster.
    """
    return get_job_event_broadcaster()


@lru_cache()
def get_templates() -> Jinja2Templates:
    """
    Provide a Jinja2Templates singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    template_path = get_template_directory()
    return Jinja2Templates(directory=template_path)


_job_manager_instance = None


def get_job_manager_dependency() -> "JobManagerProtocol":
    """
    Provide a JobManager singleton instance for FastAPI dependency injection.

    Now uses the new sub-service DI system while maintaining backward compatibility.
    """
    global _job_manager_instance
    if _job_manager_instance is None:
        import os
        from borgitory.services.jobs.job_manager import (
            JobManager,
            JobManagerConfig,
            JobManagerDependencies,
            JobManagerFactory,
        )

        # Create configuration from environment
        config = JobManagerConfig(
            max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
            max_output_lines_per_job=int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000")),
            max_concurrent_operations=int(
                os.getenv("BORG_MAX_CONCURRENT_OPERATIONS", "10")
            ),
            queue_poll_interval=float(os.getenv("BORG_QUEUE_POLL_INTERVAL", "0.1")),
            sse_keepalive_timeout=float(
                os.getenv("BORG_SSE_KEEPALIVE_TIMEOUT", "30.0")
            ),
            sse_max_queue_size=int(os.getenv("BORG_SSE_MAX_QUEUE_SIZE", "100")),
            max_concurrent_cloud_uploads=int(
                os.getenv("BORG_MAX_CONCURRENT_CLOUD_UPLOADS", "3")
            ),
        )

        # Create dependencies using our new DI services (resolved directly)
        custom_dependencies = JobManagerDependencies(
            job_executor=get_job_executor(),
            output_manager=get_job_output_manager(),
            queue_manager=get_job_queue_manager(),
            database_manager=get_job_database_manager(),
            event_broadcaster=get_job_event_broadcaster_dep(),
            rclone_service=get_rclone_service(),
            notification_service=get_notification_service_singleton(),
            # Add cloud sync dependencies
            encryption_service=get_encryption_service(),
            storage_factory=get_storage_factory(get_rclone_service()),
            provider_registry=get_provider_registry(),
        )

        # Use the factory to ensure all dependencies are properly initialized
        dependencies = JobManagerFactory.create_dependencies(
            config=config, custom_dependencies=custom_dependencies
        )

        _job_manager_instance = JobManager(config=config, dependencies=dependencies)

    return _job_manager_instance


def get_job_service(
    db: Session = Depends(get_db),
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> JobService:
    """
    Provide a JobService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return JobService(db, job_manager)


def get_borg_service(
    command_runner: "CommandRunnerProtocol" = Depends(get_simple_command_runner),
    volume_service: "VolumeServiceProtocol" = Depends(get_volume_service),
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> BorgService:
    """
    Provide a BorgService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return BorgService(
        command_runner=command_runner,
        volume_service=volume_service,
        job_manager=job_manager,
    )


def get_job_stream_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> JobStreamService:
    """
    Provide a JobStreamService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return JobStreamService(job_manager)


def get_job_render_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> JobRenderService:
    """
    Provide a JobRenderService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return JobRenderService(job_manager=job_manager)


def get_debug_service(
    volume_service: "VolumeServiceProtocol" = Depends(get_volume_service),
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> DebugService:
    """
    Provide a DebugService instance with proper dependency injection.
    Uses FastAPI DI with automatic dependency resolution.
    """
    return DebugService(volume_service=volume_service, job_manager=job_manager)


def get_repository_service(
    borg_service: BorgService = Depends(get_borg_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    volume_service: VolumeService = Depends(get_volume_service),
) -> RepositoryService:
    """
    Provide a RepositoryService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return RepositoryService(
        borg_service=borg_service,
        scheduler_service=scheduler_service,
        volume_service=volume_service,
    )


@lru_cache()
def get_provider_registry() -> ProviderRegistry:
    """
    Provide a ProviderRegistry singleton instance with proper dependency injection.

    Uses FastAPI's built-in caching for singleton behavior.
    Ensures all cloud storage providers are registered by importing the storage modules.
    """
    # Use the factory to ensure all providers are properly registered
    from borgitory.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_production_registry()


def get_schedule_service(
    db: Session = Depends(get_db),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleService:
    """
    Provide a ScheduleService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return ScheduleService(db=db, scheduler_service=scheduler_service)


@lru_cache()
def get_configuration_service() -> ConfigurationService:
    """
    Provide a ConfigurationService singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return ConfigurationService()


def get_repository_check_config_service(
    db: Session = Depends(get_db),
) -> RepositoryCheckConfigService:
    """
    Provide a RepositoryCheckConfigService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return RepositoryCheckConfigService(db=db)


def get_cleanup_service(db: Session = Depends(get_db)) -> CleanupService:
    """
    Provide a CleanupService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return CleanupService(db=db)


@lru_cache()
def get_cron_description_service() -> CronDescriptionService:
    """
    Provide a CronDescriptionService singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    """
    return CronDescriptionService()


def get_upcoming_backups_service(
    cron_description_service: CronDescriptionService = Depends(
        get_cron_description_service
    ),
) -> UpcomingBackupsService:
    """Provide UpcomingBackupsService instance."""
    return UpcomingBackupsService(cron_description_service)


def get_encryption_service() -> EncryptionService:
    """Provide an EncryptionService instance."""
    return EncryptionService()


def get_storage_factory(
    rclone: RcloneService = Depends(get_rclone_service),
) -> StorageFactory:
    """Provide a StorageFactory instance with injected RcloneService."""
    return StorageFactory(rclone)


@lru_cache()
def get_cloud_provider_service_factory() -> "CloudProviderServiceFactory":
    """
    Provide CloudProviderServiceFactory singleton instance.

    Uses FastAPI's built-in caching for singleton behavior.
    Following the exact pattern of NotificationProviderFactory.
    """
    from borgitory.factories.service_factory import CloudProviderServiceFactory

    return CloudProviderServiceFactory()


def get_cloud_sync_service(
    db: Session = Depends(get_db),
    factory: "CloudProviderServiceFactory" = Depends(
        get_cloud_provider_service_factory
    ),
) -> "CloudSyncServiceProtocol":
    """
    Provide a CloudSyncService instance using factory pattern with proper DI.

    Request-scoped since it depends on database session.
    Uses factory for consistent DI pattern across all services.
    """
    # **DI CHECK**: Using factory pattern with request-scoped db injection
    return factory.create_cloud_sync_service("default", db=db)


# 📋 SEMANTIC TYPE ALIASES FOR DEPENDENCY INJECTION
#
# These type aliases express the INTENDED USAGE PATTERN and LIFECYCLE:
# - ApplicationScoped* = Singleton instances for app-wide services (JobManager, background tasks)
# - RequestScoped* = Per-request instances via FastAPI DI (API endpoints)
#
# This makes the architectural intent crystal clear and prevents misuse.

# Core Services - Request Scoped (FastAPI Endpoints)
RequestScopedSimpleCommandRunner = Annotated[
    SimpleCommandRunner, Depends(get_simple_command_runner)
]
RequestScopedBorgService = Annotated[BorgService, Depends(get_borg_service)]
RequestScopedJobService = Annotated[JobService, Depends(get_job_service)]
RequestScopedJobManager = Annotated[JobManager, Depends(get_job_manager_dependency)]
RequestScopedRecoveryService = Annotated[RecoveryService, Depends(get_recovery_service)]

# Notification Service - Dual Scoped (Most Complex Example)
ApplicationScopedNotificationService = NotificationService  # Application-wide singleton
RequestScopedNotificationService = Annotated[
    NotificationService, Depends(get_notification_service)
]  # Per-request instance via FastAPI DI

# Legacy aliases for backward compatibility (deprecated)
SimpleCommandRunnerDep = RequestScopedSimpleCommandRunner
BorgServiceDep = RequestScopedBorgService
JobServiceDep = RequestScopedJobService
JobManagerDep = RequestScopedJobManager
RecoveryServiceDep = RequestScopedRecoveryService
NotificationConfigServiceDep = Annotated[
    NotificationConfigService, Depends(get_notification_config_service)
]
NotificationRegistryFactoryDep = Annotated[
    "NotificationRegistryFactory", Depends(get_notification_registry_factory)
]
NotificationProviderRegistryDep = Annotated[
    "NotificationProviderRegistry", Depends(get_notification_provider_registry)
]
HttpClientDep = Annotated["HttpClient", Depends(get_http_client)]
NotificationProviderFactoryDep = Annotated[
    "NotificationProviderFactory", Depends(get_notification_provider_factory)
]
CloudProviderServiceFactoryDep = Annotated[
    "CloudProviderServiceFactory", Depends(get_cloud_provider_service_factory)
]
JobStreamServiceDep = Annotated[JobStreamService, Depends(get_job_stream_service)]
JobRenderServiceDep = Annotated[JobRenderService, Depends(get_job_render_service)]
DebugServiceDep = Annotated[DebugService, Depends(get_debug_service)]
RcloneServiceDep = Annotated[RcloneService, Depends(get_rclone_service)]
RepositoryStatsServiceDep = Annotated[
    RepositoryStatsService, Depends(get_repository_stats_service)
]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
VolumeServiceDep = Annotated[VolumeService, Depends(get_volume_service)]
TaskDefinitionBuilderDep = Annotated[
    TaskDefinitionBuilder, Depends(get_task_definition_builder)
]
RepositoryParserDep = Annotated[RepositoryParser, Depends(get_repository_parser)]
BorgCommandBuilderDep = Annotated[BorgCommandBuilder, Depends(get_borg_command_builder)]
ArchiveManagerDep = Annotated[ArchiveManager, Depends(get_archive_manager)]
RepositoryServiceDep = Annotated[RepositoryService, Depends(get_repository_service)]
JobEventBroadcasterDep = Annotated[
    JobEventBroadcaster, Depends(get_job_event_broadcaster_dep)
]
TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]
ScheduleServiceDep = Annotated[ScheduleService, Depends(get_schedule_service)]
ConfigurationServiceDep = Annotated[
    ConfigurationService, Depends(get_configuration_service)
]
RepositoryCheckConfigServiceDep = Annotated[
    RepositoryCheckConfigService, Depends(get_repository_check_config_service)
]
JobExecutorDep = Annotated[JobExecutor, Depends(get_job_executor)]
JobOutputManagerDep = Annotated[JobOutputManager, Depends(get_job_output_manager)]
JobQueueManagerDep = Annotated[JobQueueManager, Depends(get_job_queue_manager)]
JobDatabaseManagerDep = Annotated[JobDatabaseManager, Depends(get_job_database_manager)]
EncryptionServiceDep = Annotated[EncryptionService, Depends(get_encryption_service)]
StorageFactoryDep = Annotated[StorageFactory, Depends(get_storage_factory)]
CleanupServiceDep = Annotated[CleanupService, Depends(get_cleanup_service)]
CronDescriptionServiceDep = Annotated[
    CronDescriptionService, Depends(get_cron_description_service)
]
UpcomingBackupsServiceDep = Annotated[
    UpcomingBackupsService, Depends(get_upcoming_backups_service)
]
CloudSyncServiceDep = Annotated["CloudSyncService", Depends(get_cloud_sync_service)]
ProviderRegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]


@lru_cache()
def get_archive_mount_manager() -> "ArchiveMountManager":
    """Get the ArchiveMountManager instance."""
    from borgitory.services.archives.archive_mount_manager import ArchiveMountManager
    from borgitory.services.jobs.job_executor import JobExecutor

    return ArchiveMountManager(job_executor=JobExecutor())


ArchiveMountManagerDep = Annotated[
    "ArchiveMountManager", Depends(get_archive_mount_manager)
]
