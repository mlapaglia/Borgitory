"""
Tests for job stop functionality
"""

import uuid
import pytest
from unittest.mock import Mock, AsyncMock
from borgitory.services.jobs.job_service import JobService
from borgitory.models.job_results import JobStopResult, JobStopError


class TestJobStopFunctionality:
    """Test job stopping functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.mock_job_manager = Mock()
        self.job_service = JobService(self.mock_db, self.mock_job_manager)

    @pytest.mark.asyncio
    async def test_stop_job_success(self) -> None:
        """Test successful job stopping"""
        # Mock job manager stop_job response
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": True,
                "message": "Job stopped successfully. 2 tasks skipped.",
                "tasks_skipped": 2,
                "current_task_killed": True,
            }
        )

        job_id = uuid.uuid4()
        result = await self.job_service.stop_job(job_id)

        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.job_id == job_id
        assert result.message == "Job stopped successfully. 2 tasks skipped."
        assert result.tasks_skipped == 2
        assert result.current_task_killed is True

    @pytest.mark.asyncio
    async def test_stop_job_not_found(self) -> None:
        """Test stopping non-existent job"""
        # Mock job manager stop_job response for not found
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }
        )

        job_id = uuid.uuid4()
        result = await self.job_service.stop_job(job_id)

        assert isinstance(result, JobStopError)
        assert result.job_id == job_id
        assert result.error == "Job not found"
        assert result.error_code == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_stop_job_invalid_status(self) -> None:
        """Test stopping job in invalid status"""
        # Mock job manager stop_job response for invalid status
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Cannot stop job in status: completed",
                "error_code": "INVALID_STATUS",
            }
        )

        job_id = uuid.uuid4()
        result = await self.job_service.stop_job(job_id)

        assert isinstance(result, JobStopError)
        assert result.job_id == job_id
        assert "Cannot stop job in status: completed" in result.error
        assert result.error_code == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_stop_job_no_tasks_skipped(self) -> None:
        """Test stopping job with no remaining tasks"""
        # Mock job manager stop_job response with no tasks skipped
        self.mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": True,
                "message": "Job stopped successfully. 0 tasks skipped.",
                "tasks_skipped": 0,
                "current_task_killed": True,
            }
        )

        job_id = uuid.uuid4()
        result = await self.job_service.stop_job(job_id)

        assert isinstance(result, JobStopResult)
        assert result.success is True
        assert result.tasks_skipped == 0
        assert result.current_task_killed is True
