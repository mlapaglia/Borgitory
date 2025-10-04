"""
Cloud Sync Task Executor - Handles cloud sync task execution
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask

logger = logging.getLogger(__name__)


class CloudSyncTaskExecutor:
    """Handles cloud sync task execution"""

    def __init__(self, job_executor: Any, output_manager: Any, event_broadcaster: Any):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    async def execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a cloud sync task using JobExecutor"""
        params = task.parameters

        if job.repository_id is None:
            task.status = "failed"
            task.error = "Repository ID is missing"
            return False
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository not found"
            task.completed_at = now_utc()
            return False

        repository_path = repo_data.get("path") or params.get("repository_path")
        passphrase = str(repo_data.get("passphrase") or params.get("passphrase") or "")

        # Validate required parameters
        if not repository_path:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository path is required for cloud sync"
            task.completed_at = now_utc()
            return False

        if not passphrase:
            task.status = "failed"
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
                "JOB_OUTPUT",
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
            task.status = "completed"
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

        # Get dependencies from the job manager
        dependencies = await self._get_dependencies()
        if not dependencies:
            task.status = "failed"
            task.error = "Missing required cloud sync dependencies"
            return False

        # Create a wrapper to convert context manager to direct session
        db_factory = dependencies["db_session_factory"]

        def session_factory():
            return db_factory().__enter__()

        result = await self.job_executor.execute_cloud_sync_task(
            repository_path=str(repository_path or ""),
            cloud_sync_config_id=cloud_sync_config_id,
            db_session_factory=session_factory,
            rclone_service=dependencies["rclone_service"],
            encryption_service=dependencies["encryption_service"],
            storage_factory=dependencies["storage_factory"],
            provider_registry=dependencies["provider_registry"],
            output_callback=task_output_callback,
        )

        task.return_code = result.return_code
        task.status = "completed" if result.return_code == 0 else "failed"
        task.completed_at = now_utc()
        if result.error:
            task.error = result.error

        return bool(result.return_code == 0)

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data by ID - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None

    async def _get_dependencies(self) -> Optional[Dict[str, Any]]:
        """Get dependencies - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None
