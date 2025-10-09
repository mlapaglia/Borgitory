"""
Tests for notification message generation with hook failures.
"""

import uuid
from typing import List, Optional
from unittest.mock import Mock, AsyncMock


from borgitory.models.job_results import JobStatusEnum
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.utils.datetime_utils import now_utc


class TestNotificationMessagesHookFailures:
    """Test notification message generation for various hook failure scenarios."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        # Create proper test dependencies using the factory
        mock_subprocess = AsyncMock()
        mock_rclone = Mock()

        self.dependencies = JobManagerFactory.create_for_testing(
            mock_subprocess=mock_subprocess,
            mock_rclone_service=mock_rclone,
        )
        self.job_manager = JobManager(dependencies=self.dependencies)

    def create_test_job(self, tasks: List[BorgJobTask]) -> BorgJob:
        """Helper to create test job with tasks."""
        job = BorgJob(
            id=uuid.uuid4(),
            job_type="composite",
            repository_id=1,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=tasks,
        )
        return job

    def create_hook_task(
        self,
        hook_type: str,
        status: TaskStatusEnum = TaskStatusEnum.PENDING,
        critical_failure: bool = False,
        failed_hook_name: Optional[str] = None,
    ) -> BorgJobTask:
        """Helper to create hook task."""
        task = BorgJobTask(
            task_type=TaskTypeEnum.HOOK,
            task_name=f"{hook_type}-job hooks",
            status=status,
            parameters={"hook_type": hook_type, "repository_name": "test-repo"},
        )

        if critical_failure:
            task.parameters["critical_failure"] = True
            if failed_hook_name:
                task.parameters["failed_critical_hook_name"] = failed_hook_name

        return task

    def create_backup_task(
        self, status: TaskStatusEnum = TaskStatusEnum.PENDING
    ) -> BorgJobTask:
        """Helper to create backup task."""
        return BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Backup repository",
            status=status,
            parameters={"repository_name": "test-repo"},
        )

    def test_critical_hook_failure_notification_message(self) -> None:
        """Test notification message for critical hook failure."""
        # Create job with critical hook failure
        failed_hook_task = self.create_hook_task(
            "pre",
            status=TaskStatusEnum.FAILED,
            critical_failure=True,
            failed_hook_name="Database Backup",
        )
        backup_task = self.create_backup_task(status=TaskStatusEnum.SKIPPED)
        post_hook_task = self.create_hook_task("post", status=TaskStatusEnum.SKIPPED)

        tasks = [failed_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify critical hook failure message
        assert "❌ Backup Job Failed - Critical Hook Error" in title
        assert "critical hook failure" in message.lower()
        assert "Database Backup" in message
        assert "Tasks Completed: 0, Skipped: 2, Total: 3" in message
        assert str(job.id) in message
        assert msg_type == "error"
        assert priority == 1  # HIGH priority

    def test_backup_failure_notification_message(self) -> None:
        """Test notification message for backup task failure."""
        # Create job with backup failure
        pre_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        failed_backup_task = self.create_backup_task(status=TaskStatusEnum.FAILED)
        post_hook_task = self.create_hook_task("post", status=TaskStatusEnum.SKIPPED)

        tasks = [pre_hook_task, failed_backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify backup failure message
        assert "❌ Backup Job Failed - Backup Error" in title
        assert "backup process" in message.lower()
        assert "Tasks Completed: 1, Skipped: 1, Total: 3" in message
        assert msg_type == "error"
        assert priority == 1  # HIGH priority

    def test_non_critical_hook_failure_notification_message(self) -> None:
        """Test notification message for non-critical hook failure."""
        # Create job with non-critical hook failure
        pre_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        backup_task = self.create_backup_task(status=TaskStatusEnum.COMPLETED)
        failed_post_hook_task = self.create_hook_task(
            "post", status=TaskStatusEnum.FAILED
        )

        tasks = [pre_hook_task, backup_task, failed_post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify warning message for non-critical failure
        assert "⚠️ Backup Job Completed with Warnings" in title
        assert "some tasks failed" in message.lower()
        assert "Failed Tasks: hook" in message
        assert "Tasks Completed: 2, Skipped: 0, Total: 3" in message
        assert msg_type == "warning"
        assert priority == 0  # NORMAL priority

    def test_successful_job_notification_message(self) -> None:
        """Test notification message for successful job."""
        # Create job with all successful tasks
        pre_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        backup_task = self.create_backup_task(status=TaskStatusEnum.COMPLETED)
        post_hook_task = self.create_hook_task("post", status=TaskStatusEnum.COMPLETED)

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify success message
        assert "✅ Backup Job Completed Successfully" in title
        assert "completed successfully" in message.lower()
        assert "Tasks Completed: 3, Total: 3" in message
        assert "Skipped:" not in message  # No skipped tasks
        assert msg_type == "success"
        assert priority == 0  # NORMAL priority

    def test_successful_job_with_skipped_tasks_notification_message(self) -> None:
        """Test notification message for successful job with some skipped tasks."""
        # Create job with successful and skipped tasks (non-critical failure scenario)
        pre_hook_task = self.create_hook_task(
            "pre", status=TaskStatusEnum.FAILED
        )  # Non-critical
        backup_task = self.create_backup_task(status=TaskStatusEnum.COMPLETED)
        post_hook_task = self.create_hook_task("post", status=TaskStatusEnum.SKIPPED)

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Should be warning due to failed task
        assert "⚠️ Backup Job Completed with Warnings" in title
        assert "Tasks Completed: 1, Skipped: 1, Total: 3" in message

    def test_notification_message_with_repository_name_from_repo(self) -> None:
        """Test notification message extracts repository name from task parameters."""
        # Create job with repository name in task parameters
        pre_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        pre_hook_task.parameters["repository_name"] = "MyBackupRepo"

        tasks = [pre_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(
                job, "MyBackupRepo"
            )
        )

        # Verify repository name is included
        assert "MyBackupRepo" in message

    def test_notification_message_unknown_repository(self) -> None:
        """Test notification message with unknown repository name."""
        # Create job without repository name
        pre_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        del pre_hook_task.parameters["repository_name"]

        tasks = [pre_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify fallback to "Unknown"
        assert "Unknown" in message

    def test_notification_message_multiple_failed_task_types(self) -> None:
        """Test notification message with multiple failed task types."""
        # Create job with multiple different failed tasks
        failed_hook_task = self.create_hook_task("pre", status=TaskStatusEnum.FAILED)
        completed_backup_task = self.create_backup_task(status=TaskStatusEnum.COMPLETED)
        failed_post_hook_task = self.create_hook_task(
            "post", status=TaskStatusEnum.FAILED
        )

        # Add a different task type
        notification_task = BorgJobTask(
            task_type=TaskTypeEnum.NOTIFICATION,
            task_name="Send notification",
            status=TaskStatusEnum.FAILED,
            parameters={},
        )

        tasks = [
            failed_hook_task,
            completed_backup_task,
            failed_post_hook_task,
            notification_task,
        ]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify multiple task types are listed
        assert "Failed Tasks: hook, hook, notification" in message
        assert "Tasks Completed: 1, Skipped: 0, Total: 4" in message

    def test_notification_message_edge_case_all_skipped(self) -> None:
        """Test notification message when all tasks are skipped (edge case)."""
        # Create job where all tasks are skipped (e.g., critical pre-hook failed before any execution)
        pre_hook_task = self.create_hook_task(
            "pre", status=TaskStatusEnum.FAILED, critical_failure=True
        )
        backup_task = self.create_backup_task(status=TaskStatusEnum.SKIPPED)
        post_hook_task = self.create_hook_task("post", status=TaskStatusEnum.SKIPPED)

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )

        # Verify critical failure message with all skipped
        assert "❌ Backup Job Failed - Critical Hook Error" in title
        assert "Tasks Completed: 0, Skipped: 2, Total: 3" in message

    def test_notification_message_priority_levels(self) -> None:
        """Test notification message priority levels for different scenarios."""
        # Test critical failure - HIGH priority
        critical_task = self.create_hook_task(
            "pre", status=TaskStatusEnum.FAILED, critical_failure=True
        )
        job = self.create_test_job([critical_task])

        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )
        assert priority == 1  # HIGH priority

        # Test non-critical failure - NORMAL priority
        normal_task = self.create_hook_task("pre", status=TaskStatusEnum.FAILED)
        job = self.create_test_job([normal_task])

        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )
        assert priority == 0  # NORMAL priority

        # Test success - NORMAL priority
        success_task = self.create_hook_task("pre", status=TaskStatusEnum.COMPLETED)
        job = self.create_test_job([success_task])

        title, message, msg_type, priority = (
            self.job_manager.notification_executor._generate_notification_content(job)
        )
        assert priority == 0  # NORMAL priority
