"""
Tests for job stop functionality at the service layer
Tests business logic directly without mocking
"""

import uuid
from unittest.mock import Mock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.services.jobs.job_service import JobService
from borgitory.models.job_results import JobStopResult, JobStopError
from borgitory.models.database import Repository, Job
from borgitory.utils.datetime_utils import now_utc
from borgitory.models.job_results import JobStatusEnum
from borgitory.protocols.job_protocols import JobManagerProtocol
from borgitory.models.database import StringUUID


class TestJobStopService:
    """Test job stop functionality at the service layer"""

    def setup_method(self) -> None:
        """Set up test fixtures with proper DI"""
        self.mock_job_manager = AsyncMock(spec=JobManagerProtocol)
        self.job_service = JobService(job_manager=self.mock_job_manager)

    async def test_stop_composite_job_success(self) -> None:
        """Test stopping a composite job successfully"""
        # Arrange
        job_id = uuid.uuid4()
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

    async def test_stop_composite_job_not_found(self) -> None:
        """Test stopping non-existent composite job"""
        # Arrange
        job_id = uuid.uuid4()
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

    async def test_stop_composite_job_invalid_status(self) -> None:
        """Test stopping composite job in invalid status"""
        # Arrange
        job_id = uuid.uuid4()
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

    async def test_stop_database_job_success(self, test_db: AsyncSession) -> None:
        """Test stopping a database job successfully"""
        # Arrange - Create real database job
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        await test_db.flush()

        job = Job()
        job.id = StringUUID(uuid.uuid4().hex)  # UUID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = JobStatusEnum.RUNNING
        job.started_at = now_utc()
        test_db.add(job)
        await test_db.commit()

        # Configure mock to return success
        self.mock_job_manager.stop_job.return_value = {
            "success": True,
            "message": "Database job stopped successfully",
            "tasks_skipped": 0,
            "current_task_killed": False,
        }

        # Use real database in service
        job_service = JobService(self.mock_job_manager)

        # Act
        result = await job_service.stop_job(job.id)

        # Assert
        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.job_id == job.id
        assert result.message == "Database job stopped successfully"
        assert result.tasks_skipped == 0
        assert result.current_task_killed is False

        # Note: Database updates are handled by the job manager, not the job service
        # The job service only orchestrates the call to the job manager

    async def test_stop_database_job_invalid_status(
        self, test_db: AsyncSession
    ) -> None:
        """Test stopping database job in invalid status"""
        # Arrange - Create completed database job
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        await test_db.flush()

        job = Job()
        job.id = StringUUID(uuid.uuid4().hex)  # UUID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = JobStatusEnum.COMPLETED
        job.started_at = now_utc()
        job.finished_at = now_utc()
        test_db.add(job)
        await test_db.commit()

        # Configure mock to return error for invalid status
        self.mock_job_manager.stop_job.return_value = {
            "success": False,
            "error": "Cannot stop job in status: completed",
            "error_code": "INVALID_STATUS",
        }

        # Use real database in service
        job_service = JobService(self.mock_job_manager)

        # Act
        result = await job_service.stop_job(job.id)

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == job.id
        assert "Cannot stop job in status: completed" in result.error
        assert result.error_code == "INVALID_STATUS"

    async def test_stop_job_not_found_anywhere(self, test_db: AsyncSession) -> None:
        """Test stopping job that doesn't exist in manager or database"""
        # Arrange
        job_service = JobService(self.mock_job_manager)
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }
        )

        # Act
        job_id = uuid.uuid4()
        result = await job_service.stop_job(job_id)

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == job_id
        assert result.error == "Job not found"
        assert result.error_code == "JOB_NOT_FOUND"

    async def test_stop_job_no_tasks_skipped(self) -> None:
        """Test stopping job with no remaining tasks"""
        # Arrange
        job_id = uuid.uuid4()
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

    async def test_stop_job_database_exception(self, test_db: AsyncSession) -> None:
        """Test handling database exceptions during job stop"""
        # Arrange - Create job but simulate database error
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        await test_db.flush()

        job = Job()
        job.id = StringUUID(uuid.uuid4().hex)
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = JobStatusEnum.RUNNING
        job.started_at = now_utc()
        test_db.add(job)
        await test_db.commit()

        # Configure mock to return error for database exception
        self.mock_job_manager.stop_job.return_value = {
            "success": False,
            "error": "Failed to stop job: Database connection error",
            "error_code": "STOP_FAILED",
        }

        # Mock database to raise exception
        mock_db = Mock(spec=AsyncSession)
        mock_db.query.side_effect = Exception("Database connection error")
        job_service = JobService(self.mock_job_manager)

        # Act
        result = await job_service.stop_job(job.id)

        # Assert
        assert isinstance(result, JobStopError)
        assert result.job_id == job.id
        assert "Failed to stop job: Database connection error" in result.error
        assert result.error_code == "STOP_FAILED"
