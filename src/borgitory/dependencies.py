"""
FastAPI dependency providers for the application.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from borgitory.models.database import get_db
import os

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


# Global singleton instances
_simple_command_runner_instance = None
_job_manager_instance = None


def get_job_manager_dependency() -> JobManager:
    """
    Provide a JobManager singleton instance for FastAPI dependency injection.

    Uses module-level singleton pattern with environment-based configuration.
    """
    global _job_manager_instance
    if _job_manager_instance is None:
        import os
        from borgitory.services.jobs.job_manager import (
            create_job_manager,
            JobManagerConfig,
        )

        # Use environment variables or defaults
        config = JobManagerConfig(
            max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
            max_output_lines_per_job=int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000")),
        )
        _job_manager_instance = create_job_manager(config, get_rclone_service())
    return _job_manager_instance


# Define JobManagerDep here so it can be used in other dependency functions
JobManagerDep = Annotated[JobManager, Depends(get_job_manager_dependency)]


def get_simple_command_runner() -> SimpleCommandRunner:
    """
    Provide a SimpleCommandRunner singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _simple_command_runner_instance
    if _simple_command_runner_instance is None:
        _simple_command_runner_instance = SimpleCommandRunner()
    return _simple_command_runner_instance


_borg_service_instance = None


def get_borg_service() -> BorgService:
    """
    Provide a BorgService singleton instance with dependency injection.

    Uses module-level singleton pattern for now to avoid circular dependency issues.
    """
    global _borg_service_instance
    if _borg_service_instance is None:
        command_runner = get_simple_command_runner()
        volume_service = get_volume_service()
        job_manager = get_job_manager_dependency()
        _borg_service_instance = BorgService(
            command_runner=command_runner,
            volume_service=volume_service,
            job_manager=job_manager,
        )
    return _borg_service_instance


def get_job_service(
    db: Session = Depends(get_db),
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> JobService:
    """
    Provide a JobService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return JobService(db, job_manager)


def get_backup_service(db: Session = Depends(get_db)) -> BackupService:
    """
    Provide a BackupService instance with database session.

    Pure backup execution service. Job creation is handled by JobService.
    Note: This creates a new instance per request since it depends on the database session.
    """
    return BackupService(db)


_recovery_service_instance = None


def get_recovery_service() -> RecoveryService:
    """
    Provide a RecoveryService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _recovery_service_instance
    if _recovery_service_instance is None:
        _recovery_service_instance = RecoveryService()
    return _recovery_service_instance


_pushover_service_instance = None


def get_pushover_service() -> PushoverService:
    """
    Provide a PushoverService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _pushover_service_instance
    if _pushover_service_instance is None:
        _pushover_service_instance = PushoverService()
    return _pushover_service_instance


_job_stream_service_instance = None


def get_job_stream_service() -> JobStreamService:
    """
    Provide a JobStreamService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _job_stream_service_instance
    if _job_stream_service_instance is None:
        job_manager = get_job_manager_dependency()
        _job_stream_service_instance = JobStreamService(job_manager)
    return _job_stream_service_instance


_job_render_service_instance = None


def get_job_render_service() -> JobRenderService:
    """
    Provide a JobRenderService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _job_render_service_instance
    if _job_render_service_instance is None:
        job_manager = get_job_manager_dependency()
        _job_render_service_instance = JobRenderService(job_manager=job_manager)
    return _job_render_service_instance


_debug_service_instance = None


def get_debug_service() -> DebugService:
    """
    Provide a DebugService singleton instance with proper dependency injection.

    Uses module-level singleton pattern with dependency injection.
    """
    global _debug_service_instance
    if _debug_service_instance is None:
        volume_service = get_volume_service()
        _debug_service_instance = DebugService(volume_service=volume_service)
    return _debug_service_instance


_rclone_service_instance = None


def get_rclone_service() -> RcloneService:
    """
    Provide a RcloneService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _rclone_service_instance
    if _rclone_service_instance is None:
        _rclone_service_instance = RcloneService()
    return _rclone_service_instance


_repository_stats_service_instance = None


def get_repository_stats_service() -> RepositoryStatsService:
    """
    Provide a RepositoryStatsService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _repository_stats_service_instance
    if _repository_stats_service_instance is None:
        _repository_stats_service_instance = RepositoryStatsService()
    return _repository_stats_service_instance


_scheduler_service_instance = None


def get_scheduler_service() -> SchedulerService:
    """
    Provide a SchedulerService singleton instance with proper dependency injection.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _scheduler_service_instance
    if _scheduler_service_instance is None:
        job_manager = get_job_manager_dependency()

        from borgitory.services.jobs.job_service import JobService

        _scheduler_service_instance = SchedulerService(
            job_manager=job_manager, job_service_factory=JobService
        )
    return _scheduler_service_instance


_volume_service_instance = None


def get_volume_service() -> VolumeService:
    """
    Provide a VolumeService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _volume_service_instance
    if _volume_service_instance is None:
        _volume_service_instance = VolumeService()
    return _volume_service_instance


def get_task_definition_builder(db: Session = Depends(get_db)) -> TaskDefinitionBuilder:
    """
    Provide a TaskDefinitionBuilder instance with database session.

    Note: This is not cached because it needs a database session per request.
    """
    return TaskDefinitionBuilder(db)


_repository_parser_instance = None


def get_repository_parser() -> RepositoryParser:
    """
    Provide a RepositoryParser singleton instance with proper dependency injection.

    Uses module-level singleton pattern with dependency injection.
    """
    global _repository_parser_instance
    if _repository_parser_instance is None:
        command_runner = get_simple_command_runner()
        _repository_parser_instance = RepositoryParser(command_runner=command_runner)
    return _repository_parser_instance


_borg_command_builder_instance = None


def get_borg_command_builder() -> BorgCommandBuilder:
    """
    Provide a BorgCommandBuilder singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _borg_command_builder_instance
    if _borg_command_builder_instance is None:
        _borg_command_builder_instance = BorgCommandBuilder()
    return _borg_command_builder_instance


_archive_manager_instance = None


def get_archive_manager() -> ArchiveManager:
    """
    Provide an ArchiveManager singleton instance with proper dependency injection.

    Uses module-level singleton pattern with dependency injection.
    """
    global _archive_manager_instance
    if _archive_manager_instance is None:
        from borgitory.services.jobs.job_executor import JobExecutor

        job_executor = JobExecutor()
        command_builder = get_borg_command_builder()
        _archive_manager_instance = ArchiveManager(
            job_executor=job_executor, command_builder=command_builder
        )
    return _archive_manager_instance


_repository_service_instance = None


def get_repository_service() -> RepositoryService:
    """
    Provide a RepositoryService singleton instance with proper dependency injection.

    Uses module-level singleton pattern with dependency injection.
    """
    global _repository_service_instance
    if _repository_service_instance is None:
        borg_service = get_borg_service()
        scheduler_service = get_scheduler_service()
        volume_service = get_volume_service()
        _repository_service_instance = RepositoryService(
            borg_service=borg_service,
            scheduler_service=scheduler_service,
            volume_service=volume_service,
        )
    return _repository_service_instance


def get_job_event_broadcaster_dep() -> JobEventBroadcaster:
    """
    Provide the global JobEventBroadcaster instance.

    Note: This uses the global instance to ensure all components
    share the same event broadcaster.
    """
    return get_job_event_broadcaster()


_templates_instance = None


def get_templates() -> Jinja2Templates:
    """
    Provide a Jinja2Templates singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _templates_instance
    if _templates_instance is None:
        base_path = "" if os.path.exists("templates") else "src/borgitory/"
        template_path = f"{base_path}templates"
        _templates_instance = Jinja2Templates(directory=template_path)
    return _templates_instance


_provider_registry_instance = None


def get_provider_registry() -> ProviderRegistry:
    """
    Provide a ProviderRegistry singleton instance with proper dependency injection.

    Ensures all cloud storage providers are registered by importing the storage modules.
    """
    global _provider_registry_instance
    if _provider_registry_instance is None:
        # Use the factory to ensure all providers are properly registered
        from borgitory.services.cloud_providers.registry_factory import RegistryFactory

        _provider_registry_instance = RegistryFactory.create_production_registry()
    return _provider_registry_instance


def get_schedule_service(
    db: Session = Depends(get_db),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
) -> ScheduleService:
    """
    Provide a ScheduleService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return ScheduleService(db=db, scheduler_service=scheduler_service)


_configuration_service_instance = None


def get_configuration_service() -> ConfigurationService:
    """
    Provide a ConfigurationService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _configuration_service_instance
    if _configuration_service_instance is None:
        _configuration_service_instance = ConfigurationService()
    return _configuration_service_instance


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


_cron_description_service_instance = None


def get_cron_description_service() -> CronDescriptionService:
    """
    Provide a CronDescriptionService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _cron_description_service_instance
    if _cron_description_service_instance is None:
        _cron_description_service_instance = CronDescriptionService()
    return _cron_description_service_instance


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


# Type aliases for dependency injection
SimpleCommandRunnerDep = Annotated[
    SimpleCommandRunner, Depends(get_simple_command_runner)
]
BorgServiceDep = Annotated[BorgService, Depends(get_borg_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
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
ProviderRegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]
