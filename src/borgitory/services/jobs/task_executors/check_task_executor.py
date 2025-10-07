"""
Check Task Executor - Handles repository check task execution
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import secure_borg_command
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum

logger = logging.getLogger(__name__)


class CheckTaskExecutor:
    """Handles repository check task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
    ):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    async def execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a repository check task"""
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
            keyfile_content = repo_data.get("keyfile_content")
            if keyfile_content is not None and not isinstance(keyfile_content, str):
                keyfile_content = None  # Ensure it's str or None

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            additional_args = []

            if params.get("repository_only", False):
                additional_args.append("--repository-only")
            if params.get("archives_only", False):
                additional_args.append("--archives-only")
            if params.get("verify_data", False):
                additional_args.append("--verify-data")
            if params.get("repair", False):
                additional_args.append("--repair")

            if repository_path:
                additional_args.append(str(repository_path))

            async with secure_borg_command(
                base_command="borg check",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=additional_args,
            ) as (command, env, _):
                process = await self.job_executor.start_process(command, env)

                result = await self.job_executor.monitor_process_output(
                    process, output_callback=task_output_callback
                )

                task.return_code = result.return_code
                task.status = (
                    TaskStatusEnum.COMPLETED
                    if result.return_code == 0
                    else TaskStatusEnum.FAILED
                )
                task.completed_at = now_utc()

            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output:
                    for line in full_output.split("\n"):
                        if line.strip():
                            task.output_lines.append(line)
                            asyncio.create_task(
                                self.output_manager.add_output_line(
                                    job.id, line, "stdout", {}
                                )
                            )

            if result.error:
                task.error = result.error
            elif result.return_code != 0:
                if result.stdout:
                    output_text = result.stdout.decode(
                        "utf-8", errors="replace"
                    ).strip()
                    error_lines = output_text.split("\n")[-5:] if output_text else []
                    stderr_text = (
                        "\n".join(error_lines) if error_lines else "No output captured"
                    )
                else:
                    stderr_text = "No output captured"
                task.error = (
                    f"Check failed with return code {result.return_code}: {stderr_text}"
                )

            return bool(result.return_code == 0)

        except Exception as e:
            logger.error(f"Error executing check task for job {job.id}: {str(e)}")
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = str(e)
            task.completed_at = now_utc()
            return False

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data by ID - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None
