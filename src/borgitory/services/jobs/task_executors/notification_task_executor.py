"""
Notification Task Executor - Handles notification task execution
"""

import logging
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum
from borgitory.services.notifications.service import NotificationService

logger = logging.getLogger(__name__)


class NotificationTaskExecutor:
    """Handles notification task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        session_maker: async_sessionmaker[AsyncSession],
        notification_service: NotificationService,
    ):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster
        self.session_maker = session_maker
        self.notification_service = notification_service

    async def execute_notification_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a notification task using Apprise"""
        params = task.parameters

        notification_config_id = params.get("notification_config_id") or params.get(
            "config_id"
        )
        if not notification_config_id:
            logger.info(
                "No notification configuration provided - skipping notification"
            )
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "No notification configuration"
            return False

        try:
            async with self.session_maker() as db:
                from borgitory.models.database import NotificationConfig
                from borgitory.models.database import Repository
                from borgitory.services.notifications.types import (
                    NotificationMessage,
                    NotificationType,
                )
                from sqlalchemy import select

                result = await db.execute(
                    select(NotificationConfig).where(
                        NotificationConfig.id == notification_config_id
                    )
                )
                config = result.scalar_one_or_none()

                if not config:
                    logger.info("Notification configuration not found - skipping")
                    task.status = TaskStatusEnum.SKIPPED
                    task.return_code = 0
                    return True

                if not config.enabled:
                    logger.info("Notification configuration disabled - skipping")
                    task.status = TaskStatusEnum.SKIPPED
                    task.return_code = 0
                    return True

                try:
                    stored_config = self.notification_service.load_config_from_storage(
                        config.provider, config.provider_config
                    )
                except Exception as e:
                    logger.error(f"Failed to load notification config: {e}")
                    task.status = TaskStatusEnum.FAILED
                    task.return_code = 1
                    task.error = (
                        f"Notification '{config.name}' must be re-configured: {str(e)}"
                    )
                    return False

                result = await db.execute(
                    select(Repository).where(Repository.id == job.repository_id)
                )
                repository = result.scalar_one_or_none()

                if repository:
                    repository_name = repository.name
                else:
                    repository_name = "Unknown"

                title, message, notification_type_str = (
                    self._generate_notification_content(job, repository_name)
                )

                title_param = params.get("title")
                message_param = params.get("message")
                type_param = params.get("type")

                if title_param is not None:
                    title = str(title_param)
                if message_param is not None:
                    message = str(message_param)
                if type_param is not None:
                    notification_type_str = str(type_param)

                try:
                    notification_type = NotificationType(
                        str(notification_type_str).lower()
                    )
                except ValueError:
                    notification_type = NotificationType.INFO

                notification_message = NotificationMessage(
                    title=str(title),
                    message=str(message),
                    notification_type=notification_type,
                )

                sending_line = f"Sending notification via {stored_config.service_name} to {config.name}"
                task.output_lines.append(sending_line)
                task.output_lines.append(f"Title: {title}")
                task.output_lines.append(f"Message: {message}")
                task.output_lines.append(f"Type: {notification_type.value}")

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": sending_line, "task_index": task_index},
                )

                notification_result = await self.notification_service.send_notification(
                    stored_config, notification_message
                )

                if notification_result.success:
                    result_message = "✓ Notification sent successfully"
                else:
                    result_message = f"✗ Failed to send notification: {notification_result.error or notification_result.message}"
                task.output_lines.append(result_message)
                for detail in notification_result.details:
                    task.output_lines.append(f"  {detail}")

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": result_message, "task_index": task_index},
                )

                task.status = (
                    TaskStatusEnum.COMPLETED
                    if notification_result.success
                    else TaskStatusEnum.FAILED
                )
                task.return_code = 0 if notification_result.success else 1
                if not notification_result.success:
                    task.error = (
                        notification_result.error or "Failed to send notification"
                    )

                return bool(notification_result.success)

        except Exception as e:
            logger.error(f"Error executing notification task: {e}")
            task.status = TaskStatusEnum.FAILED
            task.error = str(e)
            return False

    def _generate_notification_content(
        self, job: BorgJob, repository_name: str = "Unknown"
    ) -> Tuple[str, str, str]:
        """
        Generate notification title, message, and type based on job status.

        Args:
            job: The job to generate notification content for
            repository_name: Name of the repository to include in the notification

        Returns:
            Tuple of (title, message, type)
        """
        failed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.FAILED]
        completed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.COMPLETED]
        skipped_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.SKIPPED]

        critical_hook_failures = [
            t
            for t in failed_tasks
            if t.task_type == "hook" and t.parameters.get("critical_failure", False)
        ]
        backup_failures = [t for t in failed_tasks if t.task_type == "backup"]

        has_critical_failure = bool(critical_hook_failures or backup_failures)

        if has_critical_failure:
            if critical_hook_failures:
                failed_hook_name = str(
                    critical_hook_failures[0].parameters.get(
                        "failed_critical_hook_name", "unknown"
                    )
                )
                title = "❌ Backup Job Failed - Critical Hook Error"
                message = (
                    f"Backup job for '{repository_name}' failed due to critical hook failure.\n\n"
                    f"Failed Hook: {failed_hook_name}\n"
                    f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                    f"Job ID: {job.id}"
                )
            else:
                title = "❌ Backup Job Failed - Backup Error"
                message = (
                    f"Backup job for '{repository_name}' failed during backup process.\n\n"
                    f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                    f"Job ID: {job.id}"
                )
            return title, message, "error"

        elif failed_tasks:
            failed_task_types = [t.task_type for t in failed_tasks]
            title = "⚠️ Backup Job Completed with Warnings"
            message = (
                f"Backup job for '{repository_name}' completed but some tasks failed.\n\n"
                f"Failed Tasks: {', '.join(failed_task_types)}\n"
                f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "warning"

        else:
            title = "✅ Backup Job Completed Successfully"
            message = (
                f"Backup job for '{repository_name}' completed successfully.\n\n"
                f"Tasks Completed: {len(completed_tasks)}"
                f"{f', Skipped: {len(skipped_tasks)}' if skipped_tasks else ''}"
                f", Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "success"
