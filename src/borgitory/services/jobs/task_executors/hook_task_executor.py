"""
Hook Task Executor - Handles hook task execution
"""

import logging
from typing import Optional, Any
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum

logger = logging.getLogger(__name__)


class HookTaskExecutor:
    """Handles hook task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        hook_execution_service: Optional[Any] = None,
    ):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster
        self.hook_execution_service = hook_execution_service

    async def execute_hook_task(
        self,
        job: BorgJob,
        task: BorgJobTask,
        task_index: int = 0,
        job_has_failed: bool = False,
    ) -> bool:
        """Execute a hook task"""
        hook_execution_service = await self._get_hook_execution_service()
        if not hook_execution_service:
            logger.error("Hook execution service not available")
            task.status = TaskStatusEnum.FAILED
            task.error = "Hook execution service not configured"
            return False

        try:
            task.status = TaskStatusEnum.RUNNING
            task.started_at = now_utc()

            hook_configs_data = task.parameters.get("hooks", [])
            hook_type = str(task.parameters.get("hook_type", "unknown"))

            if not hook_configs_data:
                logger.warning(
                    f"No hook configurations found for {hook_type} hook task"
                )
                task.status = TaskStatusEnum.COMPLETED
                task.return_code = 0
                task.completed_at = now_utc()
                return True

            from borgitory.services.hooks.hook_config import HookConfigParser

            try:
                hook_configs = HookConfigParser.parse_hooks_json(
                    hook_configs_data
                    if isinstance(hook_configs_data, str)
                    else str(hook_configs_data)
                )
            except Exception as e:
                logger.error(f"Failed to parse hook configurations: {e}")
                task.status = TaskStatusEnum.FAILED
                task.error = f"Invalid hook configuration: {str(e)}"
                task.return_code = 1
                task.completed_at = now_utc()
                return False

            hook_summary = await hook_execution_service.execute_hooks(
                hooks=hook_configs,
                hook_type=hook_type,
                job_id=job.id,
                context={
                    "repository_id": str(job.repository_id)
                    if job.repository_id
                    else "unknown",
                    "task_index": str(task_index),
                    "job_type": str(job.job_type),
                },
                job_failed=job_has_failed,
            )

            error_messages = []

            for result in hook_summary.results:
                if result.output:
                    task.output_lines.append(
                        {
                            "text": f"[{result.hook_name}] {result.output}",
                            "timestamp": now_utc().isoformat(),
                        }
                    )

                if result.error:
                    task.output_lines.append(
                        {
                            "text": f"[{result.hook_name}] ERROR: {result.error}",
                            "timestamp": now_utc().isoformat(),
                        }
                    )

                if not result.success:
                    error_messages.append(
                        f"{result.hook_name}: {result.error or 'Unknown error'}"
                    )

            task.status = (
                TaskStatusEnum.COMPLETED
                if hook_summary.all_successful
                else TaskStatusEnum.FAILED
            )
            task.return_code = 0 if hook_summary.all_successful else 1
            task.completed_at = now_utc()

            if error_messages:
                if hook_summary.critical_failure:
                    task.error = (
                        f"Critical hook execution failed: {'; '.join(error_messages)}"
                    )
                else:
                    task.error = f"Hook execution failed: {'; '.join(error_messages)}"

            if hook_summary.critical_failure:
                task.parameters["critical_failure"] = True
                task.parameters["failed_critical_hook_name"] = (
                    hook_summary.failed_critical_hook_name
                )

            logger.info(
                f"Hook task {hook_type} completed with {len(hook_summary.results)} hooks "
                f"({'success' if hook_summary.all_successful else 'failure'})"
                f"{' (CRITICAL)' if hook_summary.critical_failure else ''}"
            )

            return bool(hook_summary.all_successful)

        except Exception as e:
            logger.error(f"Error executing hook task: {e}")
            task.status = TaskStatusEnum.FAILED
            task.error = str(e)
            task.return_code = 1
            task.completed_at = now_utc()
            return False

    async def _get_hook_execution_service(self) -> Optional[Any]:
        """Get hook execution service - this will be injected by the job manager"""
        return self.hook_execution_service
