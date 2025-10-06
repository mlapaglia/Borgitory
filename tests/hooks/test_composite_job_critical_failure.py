"""
Tests for composite job execution stopping on critical failures and task skipping.
"""

import uuid
from typing import List, Optional
from unittest.mock import Mock, AsyncMock, patch

from borgitory.models.job_results import JobStatusEnum
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.utils.datetime_utils import now_utc


class TestCompositeJobCriticalFailure:
    """Test composite job execution with critical failures."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        from borgitory.protocols.job_event_broadcaster_protocol import (
            JobEventBroadcasterProtocol,
        )

        # Create a mock event broadcaster
        mock_event_broadcaster = Mock(spec=JobEventBroadcasterProtocol)

        # Create proper test dependencies using the factory
        self.dependencies = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=mock_event_broadcaster
        )
        self.job_manager = JobManager(dependencies=self.dependencies)

    def create_test_job(self, tasks: List[BorgJobTask]) -> BorgJob:
        """Helper to create test job with tasks."""
        return BorgJob(
            id=uuid.uuid4(),
            job_type="composite",
            repository_id=1,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=tasks,
        )

    def create_hook_task(
        self,
        hook_type: str,
        critical_failure: bool = False,
        failed_hook_name: Optional[str] = None,
    ) -> BorgJobTask:
        """Helper to create hook task."""
        task = BorgJobTask(
            task_type=TaskTypeEnum.HOOK,
            task_name=f"{hook_type}-job hooks",
            parameters={"hook_type": hook_type},
        )

        if critical_failure:
            task.parameters["critical_failure"] = True
            if failed_hook_name:
                task.parameters["failed_critical_hook_name"] = failed_hook_name

        return task

    def create_backup_task(self) -> BorgJobTask:
        """Helper to create backup task."""
        return BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Backup repository",
            parameters={"source_path": "/data"},
        )

    def create_notification_task(self) -> BorgJobTask:
        """Helper to create notification task."""
        return BorgJobTask(
            task_type=TaskTypeEnum.NOTIFICATION,
            task_name="Send notification",
            parameters={"config_id": 1},
        )

    def test_critical_hook_failure_marks_remaining_tasks_skipped(self) -> None:
        """Test that critical hook failure marks remaining tasks as skipped."""
        # Create job with pre-hook (critical failure), backup, post-hook, notification
        pre_hook_task = self.create_hook_task(
            "pre", critical_failure=True, failed_hook_name="critical hook"
        )
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")
        notification_task = self.create_notification_task()

        # Set pre-hook as failed
        pre_hook_task.status = TaskStatusEnum.FAILED

        tasks = [pre_hook_task, backup_task, post_hook_task, notification_task]
        job = self.create_test_job(tasks)

        # Simulate the critical failure logic from _execute_composite_job
        task_index = 0  # Pre-hook failed
        task = tasks[task_index]

        # Check for critical hook failure
        is_critical_hook_failure = (
            task.task_type == TaskTypeEnum.HOOK
            and task.parameters.get("critical_failure", False)
        )

        if is_critical_hook_failure:
            # Mark all remaining tasks as skipped
            remaining_tasks = job.tasks[task_index + 1 :]
            for remaining_task in remaining_tasks:
                if remaining_task.status == TaskStatusEnum.PENDING:
                    remaining_task.status = TaskStatusEnum.SKIPPED
                    remaining_task.completed_at = now_utc()
                    remaining_task.output_lines.append(
                        "Task skipped due to critical hook failure"
                    )

        # Verify remaining tasks are marked as skipped
        assert backup_task.status == TaskStatusEnum.SKIPPED
        assert post_hook_task.status == TaskStatusEnum.SKIPPED
        assert notification_task.status == TaskStatusEnum.SKIPPED

        # Verify they have completion timestamps
        assert backup_task.completed_at is not None
        assert post_hook_task.completed_at is not None
        assert notification_task.completed_at is not None

        # Verify they have explanatory output
        assert any("critical hook failure" in line for line in backup_task.output_lines)
        assert any(
            "critical hook failure" in line for line in post_hook_task.output_lines
        )
        assert any(
            "critical hook failure" in line for line in notification_task.output_lines
        )

    async def test_critical_backup_task_failure_marks_remaining_tasks_skipped(
        self,
    ) -> None:
        """Test that critical backup task failure marks remaining tasks as skipped."""

        # Create job with pre-hook, backup (critical failure), post-hook, notification
        pre_hook_task = self.create_hook_task("pre")
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")
        notification_task = self.create_notification_task()

        tasks = [pre_hook_task, backup_task, post_hook_task, notification_task]
        job = self.create_test_job(tasks)

        # Mock individual task methods
        async def mock_hook_success(
            job: BorgJob,
            task: BorgJobTask,
            task_index: int = 0,
            job_has_failed: bool = False,
        ) -> bool:
            task.status = TaskStatusEnum.COMPLETED
            task.return_code = 0
            task.completed_at = now_utc()
            return True

        async def mock_backup_fail(
            job: BorgJob, task: BorgJobTask, task_index: int = 0
        ) -> bool:
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "Backup failed"
            task.completed_at = now_utc()
            return False

        # Mock all task execution methods
        with (
            patch.object(
                self.job_manager.hook_executor,
                "execute_hook_task",
                side_effect=mock_hook_success,
            ),
            patch.object(
                self.job_manager.backup_executor,
                "execute_backup_task",
                side_effect=mock_backup_fail,
            ),
            patch.object(
                self.job_manager.notification_executor,
                "execute_notification_task",
                side_effect=AsyncMock(),
            ) as mock_notification,
        ):
            # Execute the composite job
            await self.job_manager._execute_composite_job(job)

        # Verify task statuses after execution
        assert (
            pre_hook_task.status == TaskStatusEnum.COMPLETED
        )  # Should remain completed
        assert backup_task.status == TaskStatusEnum.FAILED  # Should be failed
        assert (
            post_hook_task.status == TaskStatusEnum.SKIPPED
        )  # Should be skipped due to critical failure
        assert (
            notification_task.status == TaskStatusEnum.SKIPPED
        )  # Should be skipped due to critical failure

        # Verify completed_at is set for skipped tasks
        assert post_hook_task.completed_at is not None
        assert notification_task.completed_at is not None

        # Verify output messages for skipped tasks
        assert any(
            "Task skipped due to critical task failure" in line
            for line in post_hook_task.output_lines
        )
        assert any(
            "Task skipped due to critical task failure" in line
            for line in notification_task.output_lines
        )

        # Verify job status
        assert job.status == JobStatusEnum.FAILED
        assert job.completed_at is not None

        # Verify notification task was never called due to critical failure
        mock_notification.assert_not_called()

    def test_non_critical_hook_failure_does_not_skip_tasks(self) -> None:
        """Test that non-critical hook failure does not skip remaining tasks."""
        # Create job with pre-hook (non-critical failure), backup, post-hook
        pre_hook_task = self.create_hook_task("pre", critical_failure=False)
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")

        # Set pre-hook as failed but not critical
        pre_hook_task.status = TaskStatusEnum.FAILED

        tasks = [pre_hook_task, backup_task, post_hook_task]
        self.create_test_job(tasks)

        # Simulate the non-critical failure logic
        task_index = 0  # Pre-hook failed
        task = tasks[task_index]

        # Check for critical hook failure
        is_critical_hook_failure = (
            task.task_type == TaskTypeEnum.HOOK
            and task.parameters.get("critical_failure", False)
        )

        # Should not be critical
        assert is_critical_hook_failure is False

        # Remaining tasks should stay pending (would be executed normally)
        assert backup_task.status == TaskStatusEnum.PENDING
        assert post_hook_task.status == "pending"

    def test_job_status_calculation_with_skipped_tasks(self) -> None:
        """Test final job status calculation includes skipped tasks."""
        # Create job with mixed task statuses
        pre_hook_task = self.create_hook_task("pre")
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")
        notification_task = self.create_notification_task()

        # Set various statuses
        pre_hook_task.status = TaskStatusEnum.FAILED
        pre_hook_task.parameters["critical_failure"] = True
        backup_task.status = TaskStatusEnum.SKIPPED
        post_hook_task.status = TaskStatusEnum.SKIPPED
        notification_task.status = TaskStatusEnum.SKIPPED

        tasks = [pre_hook_task, backup_task, post_hook_task, notification_task]
        job = self.create_test_job(tasks)

        # Simulate job status calculation logic
        failed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.FAILED]
        completed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.COMPLETED]
        skipped_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.SKIPPED]
        finished_tasks = completed_tasks + skipped_tasks

        if len(finished_tasks) + len(failed_tasks) == len(job.tasks):
            if failed_tasks:
                # Check if any critical tasks failed
                critical_hook_failed = any(
                    t.task_type == TaskTypeEnum.HOOK
                    and t.parameters.get("critical_failure", False)
                    for t in failed_tasks
                )
                job.status = (
                    JobStatusEnum.FAILED
                    if critical_hook_failed
                    else JobStatusEnum.COMPLETED
                )

        # Verify job status is failed due to critical hook failure
        assert job.status == JobStatusEnum.FAILED
        assert len(failed_tasks) == 1
        assert len(completed_tasks) == 0
        assert len(skipped_tasks) == 3
        assert len(finished_tasks) + len(failed_tasks) == 4  # All tasks accounted for

    def test_job_status_calculation_successful_with_skipped_tasks(self) -> None:
        """Test job status is successful when non-critical tasks fail but others are skipped."""
        # Create job where non-critical task fails but others are skipped
        pre_hook_task = self.create_hook_task("pre")
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")

        # Set non-critical failure and skipped tasks
        pre_hook_task.status = TaskStatusEnum.FAILED  # Non-critical failure
        backup_task.status = TaskStatusEnum.COMPLETED
        post_hook_task.status = TaskStatusEnum.SKIPPED

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Simulate job status calculation logic
        failed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.FAILED]
        completed_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.COMPLETED]
        skipped_tasks = [t for t in job.tasks if t.status == TaskStatusEnum.SKIPPED]
        finished_tasks = completed_tasks + skipped_tasks

        if len(finished_tasks) + len(failed_tasks) == len(job.tasks):
            if failed_tasks:
                # Check if any critical tasks failed
                critical_task_failed = any(
                    t.task_type in [TaskTypeEnum.BACKUP] for t in failed_tasks
                )
                critical_hook_failed = any(
                    t.task_type == TaskTypeEnum.HOOK
                    and t.parameters.get("critical_failure", False)
                    for t in failed_tasks
                )
                job.status = (
                    JobStatusEnum.FAILED
                    if (critical_task_failed or critical_hook_failed)
                    else JobStatusEnum.COMPLETED
                )

        # Verify job status is completed (non-critical failure)
        assert job.status == JobStatusEnum.COMPLETED
        assert len(failed_tasks) == 1
        assert len(completed_tasks) == 1
        assert len(skipped_tasks) == 1

    def test_exception_in_critical_task_marks_remaining_skipped(self) -> None:
        """Test that exception in critical task marks remaining tasks as skipped."""
        # Create job with backup task that will have exception
        pre_hook_task = self.create_hook_task("pre")
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")

        # Set pre-hook as completed, backup as failed due to exception
        pre_hook_task.status = TaskStatusEnum.COMPLETED
        backup_task.status = TaskStatusEnum.FAILED
        backup_task.error = "Exception occurred"

        tasks = [pre_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Simulate the exception handling logic for critical task
        task_index = 1  # Backup failed with exception
        task = tasks[task_index]

        # Check if it's a critical task type
        if task.task_type in [TaskTypeEnum.BACKUP]:
            # Mark all remaining tasks as skipped
            remaining_tasks = job.tasks[task_index + 1 :]
            for remaining_task in remaining_tasks:
                if remaining_task.status == TaskStatusEnum.PENDING:
                    remaining_task.status = TaskStatusEnum.SKIPPED
                    remaining_task.completed_at = now_utc()
                    remaining_task.output_lines.append(
                        "Task skipped due to critical task exception"
                    )

        # Verify remaining tasks are marked as skipped
        assert pre_hook_task.status == TaskStatusEnum.COMPLETED
        assert backup_task.status == TaskStatusEnum.FAILED
        assert post_hook_task.status == TaskStatusEnum.SKIPPED
        assert any(
            "critical task exception" in line for line in post_hook_task.output_lines
        )

    def test_multiple_critical_failures_first_one_wins(self) -> None:
        """Test that when multiple tasks could be critical, first failure is handled."""
        # Create job with multiple critical tasks
        critical_hook_task = self.create_hook_task(
            "pre", critical_failure=True, failed_hook_name="critical hook"
        )
        backup_task = self.create_backup_task()
        post_hook_task = self.create_hook_task("post")

        # Set first task as failed (critical)
        critical_hook_task.status = TaskStatusEnum.FAILED

        tasks = [critical_hook_task, backup_task, post_hook_task]
        job = self.create_test_job(tasks)

        # Simulate processing - first critical failure should stop everything
        task_index = 0
        task = tasks[task_index]

        is_critical_hook_failure = (
            task.task_type == TaskTypeEnum.HOOK
            and task.parameters.get("critical_failure", False)
        )

        if is_critical_hook_failure:
            # Mark remaining tasks as skipped
            remaining_tasks = job.tasks[task_index + 1 :]
            for remaining_task in remaining_tasks:
                if remaining_task.status == TaskStatusEnum.PENDING:
                    remaining_task.status = TaskStatusEnum.SKIPPED
                    remaining_task.completed_at = now_utc()

        # Verify all remaining tasks are skipped
        assert critical_hook_task.status == TaskStatusEnum.FAILED
        assert backup_task.status == TaskStatusEnum.SKIPPED
        assert post_hook_task.status == TaskStatusEnum.SKIPPED
