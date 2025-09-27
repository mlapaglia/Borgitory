"""
Tests for job stop functionality at the service layer
Tests business logic directly without mocking
"""

import pytest
from unittest.mock import Mock, AsyncMock
from sqlalchemy.orm import Session

from borgitory.services.jobs.job_service import JobService
from borgitory.models.job_results import JobStopResult, JobStopError
from borgitory.models.database import Repository, Job
from borgitory.utils.datetime_utils import now_utc


class TestJobStopService:
    """Test job stop functionality at the service layer"""

    def setup_method(self) -> None:
        """Set up test fixtures with proper DI"""
        self.mock_db = Mock(spec=Session)
        self.mock_job_manager = Mock()
        self.job_service = JobService(self.mock_db, self.mock_job_manager)

    @pytest.mark.asyncio
    async def test_stop_composite_job_success(self) -> None:
        """Test stopping a composite job successfully"""
        # Arrange
        job_id = "composite-job-uuid-123456789012"
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": True,
                "message": "Job stopped successfully. 3 tasks skipped.",
                "tasks_skipped": 3,
                "current_task_killed": True,
            }
        )

        # Act
        result = await self.job_service.stop_job(job_id)

        # Assert
        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.job_id == job_id
        assert result.message == "Job stopped successfully. 3 tasks skipped."
        assert result.tasks_skipped == 3
        assert result.current_task_killed is True
        self.mock_job_manager.stop_job.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_stop_composite_job_not_found(self) -> None:
        """Test stopping non-existent composite job"""
        # Arrange
        job_id = "non-existent-job-123456789012"
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }
        )

        # Act
        result = await self.job_service.stop_job(job_id)

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == job_id
        assert result.error == "Job not found"
        assert result.error_code == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_stop_composite_job_invalid_status(self) -> None:
        """Test stopping composite job in invalid status"""
        # Arrange
        job_id = "completed-job-123456789012"
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Cannot stop job in status: completed",
                "error_code": "INVALID_STATUS",
            }
        )

        # Act
        result = await self.job_service.stop_job(job_id)

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == job_id
        assert "Cannot stop job in status: completed" in result.error
        assert result.error_code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_stop_database_job_success(self, test_db: Session) -> None:
        """Test stopping a database job successfully"""
        # Arrange - Create real database job
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "db-job-123"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "running"
        job.started_at = now_utc()
        test_db.add(job)
        test_db.commit()

        # Use real database in service
        job_service = JobService(test_db, self.mock_job_manager)

        # Act
        result = await job_service.stop_job("db-job-123")

        # Assert
        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.job_id == "db-job-123"
        assert result.message == "Database job stopped successfully"
        assert result.tasks_skipped == 0
        assert result.current_task_killed is False

        # Verify database was updated
        updated_job = test_db.query(Job).filter(Job.id == "db-job-123").first()
        assert updated_job is not None
        assert updated_job.status == "stopped"
        assert updated_job.error == "Manually stopped by user"
        assert updated_job.finished_at is not None

    @pytest.mark.asyncio
    async def test_stop_database_job_invalid_status(self, test_db: Session) -> None:
        """Test stopping database job in invalid status"""
        # Arrange - Create completed database job
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "job123"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "completed"
        job.started_at = now_utc()
        job.finished_at = now_utc()
        test_db.add(job)
        test_db.commit()

        # Use real database in service
        job_service = JobService(test_db, self.mock_job_manager)

        # Act
        result = await job_service.stop_job("job123")

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == "job123"
        assert "Cannot stop job in status: completed" in result.error
        assert result.error_code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_stop_job_not_found_anywhere(self, test_db: Session) -> None:
        """Test stopping job that doesn't exist in manager or database"""
        # Arrange
        job_service = JobService(test_db, self.mock_job_manager)
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }
        )

        # Act
        result = await job_service.stop_job("non-existent-job-123456789012")

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == "non-existent-job-123456789012"
        assert result.error == "Job not found"
        assert result.error_code == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_stop_job_no_tasks_skipped(self) -> None:
        """Test stopping job with no remaining tasks"""
        # Arrange
        job_id = "single-task-job-123456789012"
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": True,
                "message": "Job stopped successfully. 0 tasks skipped.",
                "tasks_skipped": 0,
                "current_task_killed": True,
            }
        )

        # Act
        result = await self.job_service.stop_job(job_id)

        # Assert
        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.tasks_skipped == 0
        assert result.current_task_killed is True

    @pytest.mark.asyncio
    async def test_stop_job_database_exception(self, test_db: Session) -> None:
        """Test handling database exceptions during job stop"""
        # Arrange - Create job but simulate database error
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "error-job"
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "running"
        job.started_at = now_utc()
        test_db.add(job)
        test_db.commit()

        # Mock database to raise exception
        mock_db = Mock(spec=Session)
        mock_db.query.side_effect = Exception("Database connection error")
        job_service = JobService(mock_db, self.mock_job_manager)

        # Act
        result = await job_service.stop_job("error-job")

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == "error-job"
        assert "Failed to stop job: Database connection error" in result.error
        assert result.error_code == "STOP_FAILED"
