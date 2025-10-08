"""
Cloud Sync Task Executor - Handles cloud sync task execution
"""

import asyncio
import logging
from typing import Dict
from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.cloud_providers.service import StorageFactory
from borgitory.services.encryption_service import EncryptionService
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.rclone_service import RcloneService
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.protocols.job_database_manager_protocol import JobDatabaseManagerProtocol
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class CloudSyncTaskExecutor:
    """Handles cloud sync task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        session_maker: async_sessionmaker[AsyncSession],
        rclone_service: RcloneService,
        encryption_service: EncryptionService,
        storage_factory: StorageFactory,
        provider_registry: ProviderRegistry,
        database_manager: JobDatabaseManagerProtocol,
    ):
        self.session_maker = session_maker
        self.rclone_service = rclone_service
        self.encryption_service = encryption_service
        self.storage_factory = storage_factory
        self.provider_registry = provider_registry
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster
        self.database_manager = database_manager

    async def execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a cloud sync task using JobExecutor"""
        params = task.parameters

        if job.repository_id is None:
            task.status = TaskStatusEnum.FAILED
            task.error = "Repository ID is missing"
            return False
        repo_data = await self.database_manager.get_repository_data(job.repository_id)
        if not repo_data:
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "Repository not found"
            task.completed_at = now_utc()
            return False

        repository_path = repo_data.get("path") or params.get("repository_path")
        passphrase = str(repo_data.get("passphrase") or params.get("passphrase") or "")

        # Validate required parameters
        if not repository_path:
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "Repository path is required for cloud sync"
            task.completed_at = now_utc()
            return False

        if not passphrase:
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "Repository passphrase is required for cloud sync"
            task.completed_at = now_utc()
            return False

        def task_output_callback(line: str) -> None:
            task.output_lines.append(line)
            # Provide default progress since callback now only receives line
            progress: Dict[str, object] = {}
            asyncio.create_task(
                self.output_manager.add_output_line(job.id, line, "stdout", progress)
            )

            self.event_broadcaster.broadcast_event(
                EventType.JOB_OUTPUT,
                job_id=job.id,
                data={
                    "line": line,
                    "progress": None,  # No progress data
                    "task_index": task_index,
                },
            )

        # Get cloud sync config ID, defaulting to None if not configured
        cloud_sync_config_id_raw = params.get("cloud_sync_config_id")
        cloud_sync_config_id = (
            int(str(cloud_sync_config_id_raw or 0))
            if cloud_sync_config_id_raw is not None
            else None
        )

        # Handle skip case at caller level instead of inside executor
        if not cloud_sync_config_id:
            logger.info("No cloud backup configuration - skipping cloud sync")
            task.status = TaskStatusEnum.COMPLETED
            task.return_code = 0
            task.completed_at = now_utc()
            # Add output line for UI feedback
            task.output_lines.append("Cloud sync skipped - no configuration")
            asyncio.create_task(
                self.output_manager.add_output_line(
                    job.id, "Cloud sync skipped - no configuration", "stdout", {}
                )
            )
            return True

        result = await self.job_executor.execute_cloud_sync_task(
            repository_path=str(repository_path or ""),
            cloud_sync_config_id=cloud_sync_config_id,
            session_maker=self.session_maker,
            rclone_service=self.rclone_service,
            encryption_service=self.encryption_service,
            storage_factory=self.storage_factory,
            provider_registry=self.provider_registry,
            output_callback=task_output_callback,
        )

        task.return_code = result.return_code
        task.status = (
            TaskStatusEnum.COMPLETED
            if result.return_code == 0
            else TaskStatusEnum.FAILED
        )
        task.completed_at = now_utc()
        if result.error:
            task.error = result.error

        return bool(result.return_code == 0)
