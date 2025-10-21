"""
Compact Task Executor - Handles compact task execution
"""

import asyncio
import logging
from typing import Dict
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.protocols.job_database_manager_protocol import JobDatabaseManagerProtocol
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum

logger = logging.getLogger(__name__)


class CompactTaskExecutor:
    """Handles compact task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        database_manager: JobDatabaseManagerProtocol,
    ):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster
        self.database_manager = database_manager

    async def execute_compact_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a compact task using JobExecutor"""
        try:
            params = task.parameters

            if job.repository_id is None:
                task.status = TaskStatusEnum.FAILED
                task.error = "Repository ID is missing"
                return False
            repo_data = await self.database_manager.get_repository_data(
                job.repository_id
            )
            if not repo_data:
                task.status = TaskStatusEnum.FAILED
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = now_utc()
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = str(
                repo_data.get("passphrase") or params.get("passphrase") or ""
            )

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            result = await self.job_executor.execute_compact_task(
                repository_path=str(repository_path or ""),
                passphrase=passphrase,
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

        except Exception as e:
            logger.error(f"Exception in compact task: {str(e)}")
            task.status = TaskStatusEnum.FAILED
            task.return_code = -1
            task.error = f"Compact task failed: {str(e)}"
            task.completed_at = now_utc()
            return False
