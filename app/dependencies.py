"""
FastAPI dependency providers for the application.
"""

from functools import lru_cache
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
from app.services.job_event_broadcaster import JobEventBroadcaster, get_job_event_broadcaster


@lru_cache()
def get_simple_command_runner() -> SimpleCommandRunner:
    """
    Provide a SimpleCommandRunner instance.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return SimpleCommandRunner()


@lru_cache()
def get_borg_service() -> BorgService:
    """
    Provide a BorgService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return BorgService(command_runner=get_simple_command_runner())


@lru_cache()
def get_job_service() -> JobService:
    """
    Provide a JobService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return JobService()


@lru_cache()
def get_recovery_service() -> RecoveryService:
    """
    Provide a RecoveryService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return RecoveryService()


@lru_cache()
def get_pushover_service() -> PushoverService:
    """
    Provide a PushoverService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return PushoverService()


@lru_cache()
def get_job_stream_service() -> JobStreamService:
    """
    Provide a JobStreamService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return JobStreamService()


@lru_cache()
def get_job_render_service() -> JobRenderService:
    """
    Provide a JobRenderService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return JobRenderService()


@lru_cache()
def get_debug_service() -> DebugService:
    """
    Provide a DebugService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return DebugService()


@lru_cache()
def get_rclone_service() -> RcloneService:
    """
    Provide a RcloneService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return RcloneService()


@lru_cache()
def get_repository_stats_service() -> RepositoryStatsService:
    """
    Provide a RepositoryStatsService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return RepositoryStatsService()


@lru_cache()
def get_scheduler_service() -> SchedulerService:
    """
    Provide a SchedulerService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return SchedulerService()


@lru_cache()
def get_volume_service() -> VolumeService:
    """
    Provide a VolumeService instance with proper dependency injection.

    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return VolumeService()


def get_task_definition_builder(db: Session = Depends(get_db)) -> TaskDefinitionBuilder:
    """
    Provide a TaskDefinitionBuilder instance with database session.
    
    Note: This is not cached because it needs a database session per request.
    """
    return TaskDefinitionBuilder(db)


@lru_cache()
def get_repository_parser() -> RepositoryParser:
    """
    Provide a RepositoryParser instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return RepositoryParser(command_runner=get_simple_command_runner())


@lru_cache()
def get_borg_command_builder() -> BorgCommandBuilder:
    """
    Provide a BorgCommandBuilder instance.
    
    Using lru_cache ensures we get a singleton instance.
    """
    return BorgCommandBuilder()


@lru_cache()
def get_archive_manager() -> ArchiveManager:
    """
    Provide an ArchiveManager instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    from app.services.job_executor import JobExecutor
    return ArchiveManager(
        job_executor=JobExecutor(),
        command_builder=get_borg_command_builder()
    )


@lru_cache()
def get_cloud_sync_manager() -> CloudSyncManager:
    """
    Provide a CloudSyncManager instance.
    
    Using lru_cache ensures we get a singleton instance.
    """
    return CloudSyncManager()


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
TaskDefinitionBuilderDep = Annotated[TaskDefinitionBuilder, Depends(get_task_definition_builder)]
RepositoryParserDep = Annotated[RepositoryParser, Depends(get_repository_parser)]
BorgCommandBuilderDep = Annotated[BorgCommandBuilder, Depends(get_borg_command_builder)]
ArchiveManagerDep = Annotated[ArchiveManager, Depends(get_archive_manager)]
CloudSyncManagerDep = Annotated[CloudSyncManager, Depends(get_cloud_sync_manager)]
JobEventBroadcasterDep = Annotated[JobEventBroadcaster, Depends(get_job_event_broadcaster_dep)]
