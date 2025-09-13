"""
FastAPI dependency providers for the application.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from app.models.database import get_db

from app.services.simple_command_runner import SimpleCommandRunner
from app.services.borg_service import BorgService
from app.services.job_service import JobService
from app.services.recovery_service import RecoveryService
from app.services.pushover_service import PushoverService
from app.services.job_stream_service import JobStreamService
from app.services.job_render_service import JobRenderService
from app.services.debug_service import DebugService
from app.services.rclone_service import RcloneService
from app.services.repository_stats_service import RepositoryStatsService
from app.services.scheduler_service import SchedulerService
from app.services.task_definition_builder import TaskDefinitionBuilder
from app.services.volume_service import VolumeService
from app.services.repository_parser import RepositoryParser
from app.services.borg_command_builder import BorgCommandBuilder
from app.services.archive_manager import ArchiveManager
from app.services.cloud_sync_manager import CloudSyncManager
from app.services.repository_service import RepositoryService
from app.services.job_event_broadcaster import (
    JobEventBroadcaster,
    get_job_event_broadcaster,
)


# Global singleton instances
_simple_command_runner_instance = None

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
    Provide a BorgService singleton instance with proper dependency injection.

    Uses module-level singleton pattern with dependency injection.
    """
    global _borg_service_instance
    if _borg_service_instance is None:
        command_runner = get_simple_command_runner()
        volume_service = get_volume_service()
        _borg_service_instance = BorgService(
            command_runner=command_runner,
            volume_service=volume_service
        )
    return _borg_service_instance


_job_service_instance = None

def get_job_service() -> JobService:
    """
    Provide a JobService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _job_service_instance
    if _job_service_instance is None:
        _job_service_instance = JobService()
    return _job_service_instance


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
        _job_stream_service_instance = JobStreamService()
    return _job_stream_service_instance


_job_render_service_instance = None

def get_job_render_service() -> JobRenderService:
    """
    Provide a JobRenderService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _job_render_service_instance
    if _job_render_service_instance is None:
        _job_render_service_instance = JobRenderService()
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
    Provide a SchedulerService singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _scheduler_service_instance
    if _scheduler_service_instance is None:
        _scheduler_service_instance = SchedulerService()
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
        from app.services.job_executor import JobExecutor

        job_executor = JobExecutor()
        command_builder = get_borg_command_builder()
        _archive_manager_instance = ArchiveManager(
            job_executor=job_executor, command_builder=command_builder
        )
    return _archive_manager_instance


_cloud_sync_manager_instance = None

def get_cloud_sync_manager() -> CloudSyncManager:
    """
    Provide a CloudSyncManager singleton instance.

    Uses module-level singleton pattern for application-wide persistence.
    """
    global _cloud_sync_manager_instance
    if _cloud_sync_manager_instance is None:
        _cloud_sync_manager_instance = CloudSyncManager()
    return _cloud_sync_manager_instance


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
            volume_service=volume_service
        )
    return _repository_service_instance


def get_job_event_broadcaster_dep() -> JobEventBroadcaster:
    """
    Provide the global JobEventBroadcaster instance.

    Note: This uses the global instance to ensure all components
    share the same event broadcaster.
    """
    return get_job_event_broadcaster()


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
CloudSyncManagerDep = Annotated[CloudSyncManager, Depends(get_cloud_sync_manager)]
RepositoryServiceDep = Annotated[RepositoryService, Depends(get_repository_service)]
JobEventBroadcasterDep = Annotated[
    JobEventBroadcaster, Depends(get_job_event_broadcaster_dep)
]
