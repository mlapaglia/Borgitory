"""
Notification Task Executor - Handles notification task execution
"""

import logging
from typing import Optional, Any, Tuple
from borgitory.utils.db_session import get_db_session
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask

logger = logging.getLogger(__name__)


class NotificationTaskExecutor:
    """Handles notification task execution"""

    def __init__(self, job_executor: Any, output_manager: Any, event_broadcaster: Any):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    async def execute_notification_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a notification task using the new provider-based system"""
        params = task.parameters

        notification_config_id = params.get("notification_config_id") or params.get(
            "config_id"
        )
        if not notification_config_id:
            logger.info(
                "No notification configuration provided - skipping notification"
            )
            task.status = "failed"
            task.return_code = 1
            task.error = "No notification configuration"
            return False

        try:
            with get_db_session() as db:
                from borgitory.models.database import NotificationConfig
                from borgitory.models.database import Repository
                from borgitory.services.notifications.types import (
                    NotificationMessage,
                    NotificationType,
                    NotificationPriority,
                    NotificationConfig as NotificationConfigType,
                )

                config = (
                    db.query(NotificationConfig)
                    .filter(NotificationConfig.id == notification_config_id)
                    .first()
                )

                if not config:
                    logger.info("Notification configuration not found - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                if not config.enabled:
                    logger.info("Notification configuration disabled - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                # Get notification service from dependencies
                notification_service = await self._get_notification_service()
                if not notification_service:
                    logger.error(
                        "NotificationService not available - ensure proper DI setup"
                    )
                    task.status = "failed"
                    task.return_code = 1
                    task.error = "NotificationService not available"
                    return False

                # Load and decrypt configuration
                try:
                    decrypted_config = notification_service.load_config_from_storage(
                        config.provider, config.provider_config
                    )
                except Exception as e:
                    logger.error(f"Failed to load notification config: {e}")
                    task.status = "failed"
                    task.return_code = 1
                    task.error = f"Failed to load configuration: {str(e)}"
                    return False

                # Create notification config object
                notification_config = NotificationConfigType(
                    provider=config.provider,
                    config=dict(decrypted_config),  # Cast to dict[str, object]
                    name=config.name,
                    enabled=config.enabled,
                )

                repository = (
                    db.query(Repository)
                    .filter(Repository.id == job.repository_id)
                    .first()
                )

                if repository:
                    repository_name = repository.name
                else:
                    repository_name = "Unknown"

                title, message, notification_type_str, priority_value = (
                    self._generate_notification_content(job, repository_name)
                )

                title_param = params.get("title")
                message_param = params.get("message")
                type_param = params.get("type")
                priority_param = params.get("priority")

                if title_param is not None:
                    title = str(title_param)
                if message_param is not None:
                    message = str(message_param)
                if type_param is not None:
                    notification_type_str = str(type_param)
                if priority_param is not None:
                    try:
                        priority_value = int(str(priority_param))
                    except (ValueError, TypeError):
                        pass

                try:
                    notification_type = NotificationType(
                        str(notification_type_str).lower()
                    )
                except ValueError:
                    notification_type = NotificationType.INFO

                try:
                    priority = NotificationPriority(
                        int(str(priority_value)) if priority_value else 0
                    )
                except ValueError:
                    priority = NotificationPriority.NORMAL

                notification_message = NotificationMessage(
                    title=str(title),
                    message=str(message),
                    notification_type=notification_type,
                    priority=priority,
                )

                task.output_lines.append(
                    f"Sending {config.provider} notification to {config.name}"
                )
                task.output_lines.append(f"Title: {title}")
                task.output_lines.append(f"Message: {message}")
                task.output_lines.append(f"Type: {notification_type.value}")
                task.output_lines.append(f"Priority: {priority.value}")

                self.event_broadcaster.broadcast_event(
                    "JOB_OUTPUT",
                    job_id=job.id,
                    data={
                        "line": f"Sending {config.provider} notification to {config.name}",
                        "task_index": task_index,
                    },
                )

                result = await notification_service.send_notification(
                    notification_config, notification_message
                )

                if result.success:
                    result_message = "✓ Notification sent successfully"
                    task.output_lines.append(result_message)
                    if result.message:
                        task.output_lines.append(f"Response: {result.message}")
                else:
                    result_message = f"✗ Failed to send notification: {result.error or result.message}"
                    task.output_lines.append(result_message)

                self.event_broadcaster.broadcast_event(
                    "JOB_OUTPUT",
                    job_id=job.id,
                    data={"line": result_message, "task_index": task_index},
                )

                task.status = "completed" if result.success else "failed"
                task.return_code = 0 if result.success else 1
                if not result.success:
                    task.error = result.error or "Failed to send notification"

                return bool(result.success)

        except Exception as e:
            logger.error(f"Error executing notification task: {e}")
            task.status = "failed"
            task.error = str(e)
            return False

    def _generate_notification_content(
        self, job: BorgJob, repository_name: str = "Unknown"
    ) -> Tuple[str, str, str, int]:
        """
        Generate notification title, message, type, and priority based on job status.

        Args:
            job: The job to generate notification content for
            repository_name: Name of the repository to include in the notification

        Returns:
            Tuple of (title, message, type, priority_value)
        """
        failed_tasks = [t for t in job.tasks if t.status == "failed"]
        completed_tasks = [t for t in job.tasks if t.status == "completed"]
        skipped_tasks = [t for t in job.tasks if t.status == "skipped"]

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
            return title, message, "error", 1

        elif failed_tasks:
            failed_task_types = [t.task_type for t in failed_tasks]
            title = "⚠️ Backup Job Completed with Warnings"
            message = (
                f"Backup job for '{repository_name}' completed but some tasks failed.\n\n"
                f"Failed Tasks: {', '.join(failed_task_types)}\n"
                f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "warning", 0

        else:
            title = "✅ Backup Job Completed Successfully"
            message = (
                f"Backup job for '{repository_name}' completed successfully.\n\n"
                f"Tasks Completed: {len(completed_tasks)}"
                f"{f', Skipped: {len(skipped_tasks)}' if skipped_tasks else ''}"
                f", Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "success", 0

    async def _get_notification_service(self) -> Optional[Any]:
        """Get notification service - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None
