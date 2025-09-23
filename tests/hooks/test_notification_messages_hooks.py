"""
Tests for notification message generation with hook failures.
"""

from typing import List, Optional

from src.borgitory.services.jobs.job_manager import JobManager, BorgJob, BorgJobTask
from src.borgitory.utils.datetime_utils import now_utc


class MockDependencies:
    """Mock dependencies for JobManager testing."""

    def __init__(self) -> None:
        self.job_executor = None
        self.database_manager = None
        self.event_broadcaster = None
        self.output_manager = None
        self.hook_execution_service = None
        self.queue_manager = None
        self.notification_service = None


class TestNotificationMessagesHookFailures:
    """Test notification message generation for various hook failure scenarios."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        self.dependencies = MockDependencies()
        self.job_manager = JobManager(dependencies=self.dependencies)

    def create_test_job(self, tasks: List[BorgJobTask]) -> BorgJob:
        """Helper to create test job with tasks."""
        job = BorgJob(
            id="test-job-123",
            job_type="composite",
            repository_id=1,
            status="running",
            started_at=now_utc(),
            tasks=tasks,
        )
        return job

    def create_hook_task(
        self,
        hook_type: str,
        status: str = "pending",
        critical_failure: bool = False,
        failed_hook_name: Optional[str] = None,
    ) -> BorgJobTask:
        """Helper to create hook task."""
        task = BorgJobTask(
            task_type="hook",
            task_name=f"{hook_type}-job hooks",
            status=status,
            parameters={"hook_type": hook_type, "repository_name": "test-repo"},
        )

        if critical_failure:
            task.parameters["critical_failure"] = True
            if failed_hook_name:
                task.parameters["failed_critical_hook_name"] = failed_hook_name

        return task

    def create_backup_task(self, status: str = "pending") -> BorgJobTask:
        """Helper to create backup task."""
        return BorgJobTask(
            task_type="backup",
            task_name="Backup repository",
            status=status,
            parameters={"repository_name": "test-repo"},
        )

    def test_critical_hook_failure_notification_message(self) -> None:
        """Test notification message for critical hook failure."""
        # Create job with critical hook failure
        failed_hook_task = self.create_hook_task(
            "pre",
            status="failed",
            critical_failure=True,
            failed_hook_name="Database Backup",
        )
        backup_task = self.create_backup_task(status="skipped")
        post_hook_task = self.create_hook_task("post", status="skipped")

        tasks = [failed_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )

        # Verify critical hook failure message
        assert "❌ Backup Job Failed - Critical Hook Error" in title
        assert "critical hook failure" in message.lower()
        assert "Database Backup" in message
        assert "Tasks Completed: 0, Skipped: 2, Total: 3" in message
        assert "test-job-123" in message
        assert msg_type == "error"
        assert priority == 1  # HIGH priority

    def test_backup_failure_notification_message(self) -> None:
        """Test notification message for backup task failure."""
        # Create job with backup failure
        pre_hook_task = self.create_hook_task("pre", status="completed")
        failed_backup_task = self.create_backup_task(status="failed")
        post_hook_task = self.create_hook_task("post", status="skipped")

        tasks = [pre_hook_task, failed_backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
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
        pre_hook_task = self.create_hook_task("pre", status="completed")
        backup_task = self.create_backup_task(status="completed")
        failed_post_hook_task = self.create_hook_task("post", status="failed")

        tasks = [pre_hook_task, backup_task, failed_post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
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
        pre_hook_task = self.create_hook_task("pre", status="completed")
        backup_task = self.create_backup_task(status="completed")
        post_hook_task = self.create_hook_task("post", status="completed")

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
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
        pre_hook_task = self.create_hook_task("pre", status="failed")  # Non-critical
        backup_task = self.create_backup_task(status="completed")
        post_hook_task = self.create_hook_task("post", status="skipped")

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )

        # Should be warning due to failed task
        assert "⚠️ Backup Job Completed with Warnings" in title
        assert "Tasks Completed: 1, Skipped: 1, Total: 3" in message

    def test_notification_message_with_repository_name_from_task(self) -> None:
        """Test notification message extracts repository name from task parameters."""
        # Create job with repository name in task parameters
        pre_hook_task = self.create_hook_task("pre", status="completed")
        pre_hook_task.parameters["repository_name"] = "MyBackupRepo"

        tasks = [pre_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )

        # Verify repository name is included
        assert "MyBackupRepo" in message

    def test_notification_message_unknown_repository(self) -> None:
        """Test notification message with unknown repository name."""
        # Create job without repository name
        pre_hook_task = self.create_hook_task("pre", status="completed")
        del pre_hook_task.parameters["repository_name"]

        tasks = [pre_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )

        # Verify fallback to "Unknown"
        assert "Unknown" in message

    def test_notification_message_multiple_failed_task_types(self) -> None:
        """Test notification message with multiple failed task types."""
        # Create job with multiple different failed tasks
        failed_hook_task = self.create_hook_task("pre", status="failed")
        completed_backup_task = self.create_backup_task(status="completed")
        failed_post_hook_task = self.create_hook_task("post", status="failed")

        # Add a different task type
        notification_task = BorgJobTask(
            task_type="notification",
            task_name="Send notification",
            status="failed",
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
            self.job_manager._generate_notification_content(job, 0)
        )

        # Verify multiple task types are listed
        assert "Failed Tasks: hook, hook, notification" in message
        assert "Tasks Completed: 1, Skipped: 0, Total: 4" in message

    def test_notification_message_edge_case_all_skipped(self) -> None:
        """Test notification message when all tasks are skipped (edge case)."""
        # Create job where all tasks are skipped (e.g., critical pre-hook failed before any execution)
        pre_hook_task = self.create_hook_task(
            "pre", status="failed", critical_failure=True
        )
        backup_task = self.create_backup_task(status="skipped")
        post_hook_task = self.create_hook_task("post", status="skipped")

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Generate notification content
        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )

        # Verify critical failure message with all skipped
        assert "❌ Backup Job Failed - Critical Hook Error" in title
        assert "Tasks Completed: 0, Skipped: 2, Total: 3" in message

    def test_notification_message_priority_levels(self) -> None:
        """Test notification message priority levels for different scenarios."""
        # Test critical failure - HIGH priority
        critical_task = self.create_hook_task(
            "pre", status="failed", critical_failure=True
        )
        job = self.create_test_job([critical_task])

        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )
        assert priority == 1  # HIGH priority

        # Test non-critical failure - NORMAL priority
        normal_task = self.create_hook_task("pre", status="failed")
        job = self.create_test_job([normal_task])

        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )
        assert priority == 0  # NORMAL priority

        # Test success - NORMAL priority
        success_task = self.create_hook_task("pre", status="completed")
        job = self.create_test_job([success_task])

        title, message, msg_type, priority = (
            self.job_manager._generate_notification_content(job, 0)
        )
        assert priority == 0  # NORMAL priority
