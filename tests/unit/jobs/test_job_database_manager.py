"""
Comprehensive test suite for JobDatabaseManager

This test ensures that the JobDatabaseManager works correctly with AsyncSession.
"""

import pytest
import uuid
from typing import Any, cast
from unittest.mock import Mock, AsyncMock, patch
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJobTask, TaskTypeEnum, TaskStatusEnum
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum

from borgitory.services.jobs.job_database_manager import (
    JobDatabaseManager,
    DatabaseJobData,
)


class TestJobDatabaseManager:
    """Test suite for JobDatabaseManager"""

    @pytest.fixture
    def mock_async_session(self) -> AsyncMock:
        """Create mock async database session"""
        session = AsyncMock()
        session.add = Mock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_async_session_maker(self, mock_async_session: AsyncMock) -> Mock:
        """Create mock async session maker that returns async session"""
        maker = Mock()

        # Set up async context manager
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_async_session)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        maker.return_value = async_cm
        return maker

    @pytest.fixture
    def job_database_manager(
        self, mock_async_session_maker: Mock
    ) -> JobDatabaseManager:
        """Create JobDatabaseManager with mocked dependencies"""
        return JobDatabaseManager(async_session_maker=mock_async_session_maker)

    @pytest.fixture
    def sample_job_data(self) -> DatabaseJobData:
        """Create sample job data for testing"""
        return DatabaseJobData(
            id=uuid.uuid4(),
            repository_id=1,
            job_type="backup",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            cloud_sync_config_id=123,
        )

    def test_initialization_with_session_maker(
        self, mock_async_session_maker: Mock
    ) -> None:
        """Test that JobDatabaseManager initializes correctly with session maker"""
        manager = JobDatabaseManager(async_session_maker=mock_async_session_maker)

        assert hasattr(manager, "async_session_maker")
        assert manager.async_session_maker is not None
        assert manager.async_session_maker == mock_async_session_maker

    async def test_create_database_job_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
        sample_job_data: DatabaseJobData,
    ) -> None:
        """Test successful job creation"""
        with patch("borgitory.models.database.Job") as MockJob:
            mock_job_instance = Mock()
            mock_job_instance.id = sample_job_data.id
            MockJob.return_value = mock_job_instance

            result = await job_database_manager.create_database_job(sample_job_data)

            assert result == sample_job_data.id
            mock_async_session.add.assert_called_once()
            mock_async_session.commit.assert_called_once()
            mock_async_session.refresh.assert_called_once()

    async def test_update_job_status_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test successful job status update"""
        job_id = uuid.uuid4()

        mock_job_instance = Mock()
        mock_job_instance.id = job_id
        mock_job_instance.status = JobStatusEnum.RUNNING
        mock_job_instance.cloud_sync_config_id = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_job_instance)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.update_job_status(
            job_id=job_id,
            status=JobStatusEnum.COMPLETED,
            finished_at=now_utc(),
            output="Job completed successfully",
        )

        assert result is True
        assert mock_job_instance.status == JobStatusEnum.COMPLETED
        mock_async_session.commit.assert_called_once()

    async def test_get_job_by_uuid_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test successful job retrieval by UUID"""
        job_id = uuid.uuid4()

        mock_job_instance = Mock()
        mock_job_instance.id = job_id
        mock_job_instance.repository_id = 1
        mock_job_instance.type = "backup"
        mock_job_instance.status = JobStatusEnum.COMPLETED
        mock_job_instance.started_at = now_utc()
        mock_job_instance.finished_at = now_utc()
        mock_job_instance.log_output = "Job output"
        mock_job_instance.error = None
        mock_job_instance.cloud_sync_config_id = 123

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_job_instance)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.get_job_by_uuid(job_id)

        assert result is not None
        assert result["id"] == job_id
        assert result["repository_id"] == 1
        assert result["type"] == "backup"
        assert result["status"] == JobStatusEnum.COMPLETED
        assert result["output"] == "Job output"

    async def test_get_jobs_by_repository_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test successful job retrieval by repository"""
        repository_id = 1

        mock_job1 = Mock()
        mock_job1.id = uuid.uuid4()
        mock_job1.type = "backup"
        mock_job1.status = JobStatusEnum.COMPLETED
        mock_job1.started_at = now_utc()
        mock_job1.finished_at = now_utc()
        mock_job1.error = None

        mock_job2 = Mock()
        mock_job2.id = uuid.uuid4()
        mock_job2.type = "prune"
        mock_job2.status = JobStatusEnum.RUNNING
        mock_job2.started_at = now_utc()
        mock_job2.finished_at = None
        mock_job2.error = None

        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[mock_job1, mock_job2])

        mock_result = Mock()
        mock_result.scalars = Mock(return_value=mock_scalars)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.get_jobs_by_repository(
            repository_id, limit=10
        )

        assert len(result) == 2
        assert result[0]["id"] == mock_job1.id
        assert result[1]["id"] == mock_job2.id

    async def test_save_job_tasks_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test successful task saving"""
        job_id = uuid.uuid4()

        mock_task1 = Mock(spec=BorgJobTask)
        mock_task1.task_type = TaskTypeEnum.BACKUP
        mock_task1.task_name = "Create backup"
        mock_task1.status = TaskStatusEnum.COMPLETED
        mock_task1.started_at = now_utc()
        mock_task1.completed_at = now_utc()
        mock_task1.output_lines = ["Line 1", "Line 2"]
        mock_task1.error = None
        mock_task1.return_code = 0

        mock_task2 = Mock(spec=BorgJobTask)
        mock_task2.task_type = TaskTypeEnum.CLOUD_SYNC
        mock_task2.task_name = "Sync to cloud"
        mock_task2.status = TaskStatusEnum.RUNNING
        mock_task2.started_at = now_utc()
        mock_task2.completed_at = None
        mock_task2.output_lines = []
        mock_task2.error = None
        mock_task2.return_code = None

        tasks = [mock_task1, mock_task2]

        mock_job_instance = Mock()
        mock_job_instance.id = job_id

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_job_instance)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.save_job_tasks(
            job_id, cast(list[BorgJobTask], tasks)
        )

        assert result is True
        assert mock_job_instance.total_tasks == 2
        assert mock_job_instance.completed_tasks == 1
        mock_async_session.commit.assert_called_once()

    async def test_get_job_statistics_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test job statistics retrieval"""
        mock_status_result = Mock()
        mock_status_result.all = Mock(
            return_value=[
                (JobStatusEnum.COMPLETED, 10),
                (JobStatusEnum.RUNNING, 2),
            ]
        )

        mock_type_result = Mock()
        mock_type_result.all = Mock(
            return_value=[
                ("backup", 8),
                ("prune", 4),
            ]
        )

        mock_recent_result = Mock()
        mock_recent_result.scalar = Mock(return_value=5)

        mock_total_result = Mock()
        mock_total_result.scalar = Mock(return_value=12)

        mock_async_session.execute = AsyncMock(
            side_effect=[
                mock_status_result,
                mock_type_result,
                mock_recent_result,
                mock_total_result,
            ]
        )

        result = await job_database_manager.get_job_statistics()

        assert result["total_jobs"] == 12
        assert result["recent_jobs_24h"] == 5
        by_status = cast(dict[Any, Any], result.get("by_status", {}))
        by_type = cast(dict[Any, Any], result.get("by_type", {}))
        assert JobStatusEnum.COMPLETED in by_status
        assert "backup" in by_type

    async def test_get_repository_data_happy_path(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test repository data retrieval"""
        repository_id = 1

        mock_repo = Mock()
        mock_repo.id = repository_id
        mock_repo.name = "test-repo"
        mock_repo.path = "/path/to/repo"
        mock_repo.cache_dir = "/cache"
        mock_repo.get_passphrase = Mock(return_value="secret")
        mock_repo.get_keyfile_content = Mock(return_value=None)

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_repo)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.get_repository_data(repository_id)

        assert result is not None
        assert result["id"] == repository_id
        assert result["name"] == "test-repo"
        assert result["path"] == "/path/to/repo"

    async def test_error_handling_create_job(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test error handling in job creation"""
        mock_async_session.add.side_effect = Exception("Database error")

        sample_data = DatabaseJobData(
            id=uuid.uuid4(),
            repository_id=1,
            job_type=JobTypeEnum.BACKUP,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
        )

        result = await job_database_manager.create_database_job(sample_data)
        assert result is None

    async def test_error_handling_update_job_status(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test error handling in job status update"""
        mock_async_session.commit.side_effect = Exception("Database error")

        mock_job_instance = Mock()
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_job_instance)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.update_job_status(
            job_id=uuid.uuid4(), status=JobStatusEnum.COMPLETED
        )
        assert result is False

    async def test_get_job_statistics_error_handling(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test job statistics error handling"""
        mock_async_session.execute.side_effect = Exception("Database error")

        result = await job_database_manager.get_job_statistics()

        assert result == {}

    async def test_job_not_found_scenarios(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test scenarios where job is not found"""
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.update_job_status(
            job_id=uuid.uuid4(), status=JobStatusEnum.COMPLETED
        )
        assert result is False

        result_job = await job_database_manager.get_job_by_uuid(uuid.uuid4())
        assert result_job is None

        result = await job_database_manager.save_job_tasks(uuid.uuid4(), [])
        assert result is False

    async def test_get_repository_data_not_found(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test repository data retrieval when repository not found"""
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.get_repository_data(999)

        assert result is None

    async def test_save_job_tasks_with_dict_output_lines(
        self,
        job_database_manager: JobDatabaseManager,
        mock_async_session: AsyncMock,
    ) -> None:
        """Test task saving with dict-style output lines"""
        job_id = uuid.uuid4()

        mock_task = Mock(spec=BorgJobTask)
        mock_task.task_type = TaskTypeEnum.BACKUP
        mock_task.task_name = "Create backup"
        mock_task.status = TaskStatusEnum.COMPLETED
        mock_task.started_at = now_utc()
        mock_task.completed_at = now_utc()
        mock_task.output_lines = [
            {"text": "Line 1", "timestamp": "2024-01-01"},
            {"text": "Line 2", "timestamp": "2024-01-02"},
        ]
        mock_task.error = None
        mock_task.return_code = 0

        mock_job_instance = Mock()
        mock_job_instance.id = job_id

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_job_instance)
        mock_async_session.execute = AsyncMock(return_value=mock_result)

        result = await job_database_manager.save_job_tasks(
            job_id, cast(list[BorgJobTask], [mock_task])
        )

        assert result is True
        mock_async_session.commit.assert_called_once()
