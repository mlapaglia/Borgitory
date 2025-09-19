"""
FastAPI dependency providers for the application.
"""

from typing import Annotated, TYPE_CHECKING, Optional, Callable, Any
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
from borgitory.services.notifications.pushover_service import PushoverService
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
from borgitory.services.notifications.notification_config_service import (
    NotificationConfigService,
)
from borgitory.services.cleanup_service import CleanupService
from borgitory.services.cron_description_service import CronDescriptionService
from borgitory.services.upcoming_backups_service import UpcomingBackupsService
from fastapi.templating import Jinja2Templates
from borgitory.services.cloud_providers import EncryptionService, StorageFactory

if TYPE_CHECKING:
    from borgitory.services.cloud_sync_service import CloudSyncService
    from borgitory.protocols.command_protocols import (
        CommandRunnerProtocol,
        ProcessExecutorProtocol,
    )
    from borgitory.protocols.storage_protocols import VolumeServiceProtocol
    from borgitory.protocols.job_protocols import (
        JobManagerProtocol,
    )
    from borgitory.protocols.repository_protocols import (
        BackupServiceProtocol,
    )
    from borgitory.protocols.notification_protocols import NotificationServiceProtocol
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
    db_session_factory: Optional[Callable[[], Any]] = None,
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
def get_pushover_service() -> "NotificationServiceProtocol":
    """
    Provide a NotificationServiceProtocol implementation (PushoverService).

    Uses FastAPI's built-in caching for singleton behavior.
    Returns protocol interface for loose coupling.
    """
    return PushoverService()


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

    Uses pure FastAPI DI with automatic dependency resolution.
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
        dependencies = JobManagerDependencies(
            job_executor=get_job_executor(),
            output_manager=get_job_output_manager(),
            queue_manager=get_job_queue_manager(),
            database_manager=get_job_database_manager(),
            event_broadcaster=get_job_event_broadcaster_dep(),
            pushover_service=get_pushover_service(),
            rclone_service=get_rclone_service(),
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

    Uses pure FastAPI DI with automatic dependency resolution.
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

    Uses pure FastAPI DI with automatic dependency resolution.
    """
    return JobStreamService(job_manager)


def get_job_render_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> JobRenderService:
    """
    Provide a JobRenderService instance with proper dependency injection.

    Uses pure FastAPI DI with automatic dependency resolution.
    """
    return JobRenderService(job_manager=job_manager)


def get_debug_service(
    volume_service: "VolumeServiceProtocol" = Depends(get_volume_service),
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> DebugService:
    """
    Provide a DebugService instance with proper dependency injection.
    Uses pure FastAPI DI with automatic dependency resolution.
    """
    return DebugService(volume_service=volume_service, job_manager=job_manager)


def get_repository_service(
    borg_service: "BackupServiceProtocol" = Depends(get_borg_service),
    scheduler_service: ScheduleService = Depends(get_scheduler_service),
    volume_service: "VolumeServiceProtocol" = Depends(get_volume_service),
) -> RepositoryService:
    """
    Provide a RepositoryService instance with proper dependency injection.

    Uses pure FastAPI DI with automatic dependency resolution.
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


def get_notification_config_service(
    db: Session = Depends(get_db),
) -> NotificationConfigService:
    """
    Provide a NotificationConfigService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return NotificationConfigService(db=db)


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


def get_cloud_sync_service(
    db: Session = Depends(get_db),
    rclone_service: RcloneService = Depends(get_rclone_service),
    storage_factory: StorageFactory = Depends(get_storage_factory),
    encryption_service: EncryptionService = Depends(get_encryption_service),
) -> "CloudSyncService":
    """
    Provide a CloudSyncService instance with proper dependency injection.

    Request-scoped since it depends on database session.
    """
    from borgitory.services.cloud_sync_service import CloudSyncService
    from borgitory.services.cloud_providers.registry import get_metadata

    return CloudSyncService(
        db=db,
        rclone_service=rclone_service,
        storage_factory=storage_factory,
        encryption_service=encryption_service,
        get_metadata_func=get_metadata,
    )


# Type aliases for dependency injection
SimpleCommandRunnerDep = Annotated[
    SimpleCommandRunner, Depends(get_simple_command_runner)
]
BorgServiceDep = Annotated[BorgService, Depends(get_borg_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
JobManagerDep = Annotated[JobManager, Depends(get_job_manager_dependency)]
RecoveryServiceDep = Annotated[RecoveryService, Depends(get_recovery_service)]
PushoverServiceDep = Annotated[PushoverService, Depends(get_pushover_service)]
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
NotificationConfigServiceDep = Annotated[
    NotificationConfigService, Depends(get_notification_config_service)
]
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
def get_archive_mount_manager() -> Any:
    """Get the ArchiveMountManager instance."""
    from borgitory.services.archives.archive_mount_manager import ArchiveMountManager
    from borgitory.services.jobs.job_executor import JobExecutor

    return ArchiveMountManager(job_executor=JobExecutor())


ArchiveMountManagerDep = Annotated[Any, Depends(get_archive_mount_manager)]
