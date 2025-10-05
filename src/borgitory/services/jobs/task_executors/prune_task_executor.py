"""
Prune Task Executor - Handles prune task execution
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum

logger = logging.getLogger(__name__)


class PruneTaskExecutor:
    """Handles prune task execution"""

    def __init__(self, job_executor: Any, output_manager: Any, event_broadcaster: Any):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    async def execute_prune_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a prune task using JobExecutor"""
        try:
            params = task.parameters

            if job.repository_id is None:
                task.status = TaskStatusEnum.FAILED
                task.error = "Repository ID is missing"
                return False
            repo_data = await self._get_repository_data(job.repository_id)
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
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            result = await self.job_executor.execute_prune_task(
                repository_path=str(repository_path or ""),
                passphrase=passphrase,
                keep_within=str(params.get("keep_within"))
                if params.get("keep_within")
                else None,
                keep_secondly=int(str(params.get("keep_secondly") or 0))
                if params.get("keep_secondly")
                else None,
                keep_minutely=int(str(params.get("keep_minutely") or 0))
                if params.get("keep_minutely")
                else None,
                keep_hourly=int(str(params.get("keep_hourly") or 0))
                if params.get("keep_hourly")
                else None,
                keep_daily=int(str(params.get("keep_daily") or 0))
                if params.get("keep_daily")
                else None,
                keep_weekly=int(str(params.get("keep_weekly") or 0))
                if params.get("keep_weekly")
                else None,
                keep_monthly=int(str(params.get("keep_monthly") or 0))
                if params.get("keep_monthly")
                else None,
                keep_yearly=int(str(params.get("keep_yearly") or 0))
                if params.get("keep_yearly")
                else None,
                show_stats=bool(params.get("show_stats", True)),
                show_list=bool(params.get("show_list", False)),
                save_space=bool(params.get("save_space", False)),
                force_prune=bool(params.get("force_prune", False)),
                dry_run=bool(params.get("dry_run", False)),
                output_callback=task_output_callback,
            )

            # Set task status based on result
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
            logger.error(f"Exception in prune task: {str(e)}")
            task.status = TaskStatusEnum.FAILED
            task.return_code = -1
            task.error = f"Prune task failed: {str(e)}"
            task.completed_at = now_utc()
            return False

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data by ID - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None
