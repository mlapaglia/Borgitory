"""
Tests for JobManager stop_job functionality
Tests the business logic directly without mocking core components
"""

import pytest
from unittest.mock import Mock, AsyncMock

from borgitory.models.job_results import JobStatusEnum
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.utils.datetime_utils import now_utc


class TestJobManagerStop:
    """Test JobManager stop_job method"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.job_manager = JobManager()
        self.job_manager._initialized = True

    @pytest.mark.asyncio
    async def test_stop_job_not_found(self) -> None:
        """Test stopping non-existent job"""
        # Act
        result = await self.job_manager.stop_job("non-existent-job-id")

        # Assert
        assert result["success"] is False
        assert result["error"] == "Job not found"
        assert result["error_code"] == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_stop_job_invalid_status_completed(self) -> None:
        """Test stopping job that's already completed"""
        # Arrange
        job_id = "completed-job-id"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.COMPLETED,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is False
        assert result["error"] == "Cannot stop job in status: JobStatusEnum.COMPLETED"
        assert result["error_code"] == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_stop_job_invalid_status_failed(self) -> None:
        """Test stopping job that's already failed"""
        # Arrange
        job_id = "failed-job-id"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.FAILED,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is False
        assert result["error"] == "Cannot stop job in status: JobStatusEnum.FAILED"
        assert result["error_code"] == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_stop_simple_running_job_no_process(self) -> None:
        """Test stopping simple running job with no active process"""
        # Arrange
        job_id = "simple-running-job"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 0 tasks skipped."
        assert result["tasks_skipped"] == 0
        assert result["current_task_killed"] is False

        # Verify job state
        assert job.status == JobStatusEnum.STOPPED
        assert job.error == "Manually stopped by user"
        assert job.completed_at is not None

        # Verify database update
        mock_db_manager.update_job_status.assert_called_once_with(
            job_id, "stopped", job.completed_at
        )

    @pytest.mark.asyncio
    async def test_stop_running_job_with_process(self) -> None:
        """Test stopping running job with active process"""
        # Arrange
        job_id = "running-job-with-process"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Mock process
        mock_process = Mock()
        self.job_manager._processes[job_id] = mock_process

        # Mock executor
        mock_executor = Mock()
        mock_executor.terminate_process = AsyncMock(return_value=True)
        self.job_manager.executor = mock_executor

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 0 tasks skipped."
        assert result["tasks_skipped"] == 0
        assert result["current_task_killed"] is True

        # Verify process was terminated
        mock_executor.terminate_process.assert_called_once_with(mock_process)
        assert job_id not in self.job_manager._processes

        # Verify job state
        assert job.status == JobStatusEnum.STOPPED
        assert job.error == "Manually stopped by user"

    @pytest.mark.asyncio
    async def test_stop_running_job_process_termination_fails(self) -> None:
        """Test stopping running job when process termination fails"""
        # Arrange
        job_id = "running-job-term-fails"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Mock process
        mock_process = Mock()
        self.job_manager._processes[job_id] = mock_process

        # Mock executor - termination fails
        mock_executor = Mock()
        mock_executor.terminate_process = AsyncMock(return_value=False)
        self.job_manager.executor = mock_executor

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["current_task_killed"] is False  # Process termination failed

        # Process should still be in the dict since termination failed
        assert job_id in self.job_manager._processes

    @pytest.mark.asyncio
    async def test_stop_queued_job(self) -> None:
        """Test stopping queued job"""
        # Arrange
        job_id = "queued-job"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.QUEUED,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 0 tasks skipped."
        assert result["tasks_skipped"] == 0
        assert result["current_task_killed"] is False

        # Verify job state
        assert job.status == JobStatusEnum.STOPPED
        assert job.error == "Manually stopped by user"

    @pytest.mark.asyncio
    async def test_stop_composite_job_with_tasks(self) -> None:
        """Test stopping composite job with multiple tasks"""
        # Arrange
        job_id = "composite-job-with-tasks"

        # Create tasks
        task1 = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="create-backup",
            status=TaskStatusEnum.COMPLETED,
            started_at=now_utc(),
            completed_at=now_utc(),
        )
        task2 = BorgJobTask(
            task_type=TaskTypeEnum.PRUNE,
            task_name="prune-archives",
            status=TaskStatusEnum.RUNNING,
            started_at=now_utc(),
        )
        task3 = BorgJobTask(
            task_type=TaskTypeEnum.CHECK,
            task_name="check-repository",
            status=TaskStatusEnum.PENDING,
        )
        task4 = BorgJobTask(
            task_type=TaskTypeEnum.INFO,
            task_name="get-info",
            status=TaskStatusEnum.QUEUED,
        )

        job = BorgJob(
            id=job_id,
            command=["composite"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="composite",
            tasks=[task1, task2, task3, task4],
            current_task_index=1,  # Currently on task2 (running)
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 2 tasks skipped."
        assert result["tasks_skipped"] == 2  # task3 and task4
        assert result["current_task_killed"] is False  # No process was running

        # Verify job state
        assert job.status == "stopped"
        assert job.error == "Manually stopped by user"

        # Verify task states
        assert task1.status == "completed"  # Unchanged
        assert task2.status == "stopped"  # Current running task stopped
        assert task2.error == "Manually stopped by user"
        assert task2.completed_at is not None
        assert task3.status == TaskStatusEnum.SKIPPED  # Pending task skipped
        assert task3.error == "Skipped due to manual job stop"
        assert task3.completed_at is not None
        assert task4.status == TaskStatusEnum.SKIPPED  # Queued task skipped
        assert task4.error == "Skipped due to manual job stop"
        assert task4.completed_at is not None

    @pytest.mark.asyncio
    async def test_stop_composite_job_with_process_and_tasks(self) -> None:
        """Test stopping composite job with active process and remaining tasks"""
        # Arrange
        job_id = "composite-job-with-process"

        task1 = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="create-backup",
            status=TaskStatusEnum.RUNNING,
            started_at=now_utc(),
        )
        task2 = BorgJobTask(
            task_type=TaskTypeEnum.PRUNE,
            task_name="prune-archives",
            status=TaskStatusEnum.PENDING,
        )

        job = BorgJob(
            id=job_id,
            command=["composite"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="composite",
            tasks=[task1, task2],
            current_task_index=0,  # Currently on task1
        )
        self.job_manager.jobs[job_id] = job

        # Mock process
        mock_process = Mock()
        self.job_manager._processes[job_id] = mock_process

        # Mock executor
        mock_executor = Mock()
        mock_executor.terminate_process = AsyncMock(return_value=True)
        self.job_manager.executor = mock_executor

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 1 tasks skipped."
        assert result["tasks_skipped"] == 1  # task2
        assert result["current_task_killed"] is True  # Process was terminated

        # Verify process termination
        mock_executor.terminate_process.assert_called_once_with(mock_process)
        assert job_id not in self.job_manager._processes

        # Verify task states
        assert task1.status == TaskStatusEnum.STOPPED
        assert task1.error == "Manually stopped by user"
        assert task2.status == TaskStatusEnum.SKIPPED
        assert task2.error == "Skipped due to manual job stop"

    @pytest.mark.asyncio
    async def test_stop_composite_job_no_remaining_tasks(self) -> None:
        """Test stopping composite job on last task"""
        # Arrange
        job_id = "composite-job-last-task"

        task1 = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="create-backup",
            status=TaskStatusEnum.COMPLETED,
            started_at=now_utc(),
            completed_at=now_utc(),
        )
        task2 = BorgJobTask(
            task_type=TaskTypeEnum.PRUNE,
            task_name="prune-archives",
            status=TaskStatusEnum.RUNNING,
            started_at=now_utc(),
        )

        job = BorgJob(
            id=job_id,
            command=["composite"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="composite",
            tasks=[task1, task2],
            current_task_index=1,  # Currently on last task
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Job stopped successfully. 0 tasks skipped."
        assert result["tasks_skipped"] == 0  # No remaining tasks
        assert result["current_task_killed"] is False

        # Verify task states
        assert task1.status == TaskStatusEnum.COMPLETED  # Unchanged
        assert task2.status == TaskStatusEnum.STOPPED  # Current task stopped

    @pytest.mark.asyncio
    async def test_stop_job_event_broadcasting(self) -> None:
        """Test that stop job broadcasts the correct event"""
        # Arrange
        job_id = "job-for-event-test"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job

        # Mock event broadcaster
        mock_broadcaster = Mock()
        mock_broadcaster.broadcast_event = Mock()
        self.job_manager.event_broadcaster = mock_broadcaster

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True

        # Verify event was broadcast
        mock_broadcaster.broadcast_event.assert_called_once()
        call_args = mock_broadcaster.broadcast_event.call_args

        # Check event type and job_id
        assert call_args[0][0].name == "JOB_CANCELLED"  # EventType.JOB_CANCELLED
        assert call_args[1]["job_id"] == job_id

        # Check event data
        event_data = call_args[1]["data"]
        assert event_data["reason"] == "manual_stop"
        assert event_data["tasks_skipped"] == 0
        assert event_data["current_task_killed"] is False
        assert "stopped_at" in event_data

    @pytest.mark.asyncio
    async def test_stop_job_no_database_manager(self) -> None:
        """Test stopping job when database manager is None"""
        # Arrange
        job_id = "job-no-db-manager"
        job = BorgJob(
            id=job_id,
            command=["borg", "create"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="simple",
        )
        self.job_manager.jobs[job_id] = job
        self.job_manager.database_manager = None  # No database manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert job.status == "stopped"
        # Should not raise any errors even without database manager

    @pytest.mark.asyncio
    async def test_stop_composite_job_task_index_out_of_bounds(self) -> None:
        """Test stopping composite job with invalid current_task_index"""
        # Arrange
        job_id = "composite-job-invalid-index"

        task1 = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="create-backup",
            status=TaskStatusEnum.COMPLETED,
            started_at=now_utc(),
            completed_at=now_utc(),
        )

        job = BorgJob(
            id=job_id,
            command=["composite"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="composite",
            tasks=[task1],
            current_task_index=5,  # Out of bounds
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["tasks_skipped"] == 0  # No tasks to skip
        assert job.status == "stopped"

    @pytest.mark.asyncio
    async def test_stop_composite_job_no_tasks(self) -> None:
        """Test stopping composite job with no tasks"""
        # Arrange
        job_id = "composite-job-no-tasks"
        job = BorgJob(
            id=job_id,
            command=["composite"],
            started_at=now_utc(),
            status=JobStatusEnum.RUNNING,
            job_type="composite",
            tasks=[],  # No tasks
            current_task_index=0,
        )
        self.job_manager.jobs[job_id] = job

        # Mock database manager
        mock_db_manager = Mock()
        mock_db_manager.update_job_status = AsyncMock()
        self.job_manager.database_manager = mock_db_manager

        # Act
        result = await self.job_manager.stop_job(job_id)

        # Assert
        assert result["success"] is True
        assert result["tasks_skipped"] == 0
        assert job.status == "stopped"
