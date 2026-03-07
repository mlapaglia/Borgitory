"""
Tests for CompactTaskExecutor
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock
from contextlib import asynccontextmanager
from typing import AsyncGenerator, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskTypeEnum,
    TaskStatusEnum,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.models.database import Repository
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum


class TestCompactTaskExecutor:
    """Test compact task executor methods"""

    @pytest.fixture
    def job_manager_with_mocks(
        self,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
        mock_notification_service: Mock,
        test_db: AsyncSession,
    ) -> JobManager:
        """Create job manager with injected mock dependencies"""

        @asynccontextmanager
        async def mock_db_session_factory() -> AsyncGenerator[AsyncSession, None]:
            try:
                yield test_db
            finally:
                pass

        deps = JobManagerFactory.create_for_testing()
        deps.job_executor = mock_job_executor
        deps.database_manager = mock_database_manager
        deps.output_manager = mock_output_manager
        deps.queue_manager = mock_queue_manager
        deps.event_broadcaster = mock_event_broadcaster
        deps.notification_service = mock_notification_service
        deps.async_session_maker = cast(
            async_sessionmaker[AsyncSession], mock_db_session_factory
        )

        job_manager = JobManager(dependencies=deps)

        job_manager.output_manager = mock_output_manager
        job_manager.queue_manager = mock_queue_manager
        job_manager.event_broadcaster = mock_event_broadcaster

        return job_manager

    async def test_execute_compact_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful compact task execution"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-pass",
        }

        mock_job_executor.execute_compact_task = AsyncMock(
            return_value=ProcessResult(
                return_code=0, stdout=b"Compacting complete", stderr=b"", error=None
            )
        )

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

        mock_database_manager.get_repository_data.assert_called_once_with(1)
        mock_job_executor.execute_compact_task.assert_called_once()

    async def test_execute_compact_task_failure(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test compact task failure handling"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = {
            "id": sample_repository.id,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_job_executor.execute_compact_task = AsyncMock(
            return_value=ProcessResult(
                return_code=2,
                stdout=b"Repository locked",
                stderr=b"",
                error="Compact failed",
            )
        )

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.return_code == 2
        assert task.error is not None
        assert "Compact failed" in task.error

    async def test_execute_compact_task_missing_repository_id(
        self,
        job_manager_with_mocks: JobManager,
    ) -> None:
        """Test compact task with missing repository ID"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=None,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.error == "Repository ID is missing"

    async def test_execute_compact_task_repository_not_found(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test compact task when repository is not found"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=999,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = None

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.return_code == 1
        assert task.error == "Repository not found"
        assert task.completed_at is not None

    async def test_execute_compact_task_with_exception(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test compact task when an exception occurs"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-pass",
        }

        mock_job_executor.execute_compact_task = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.return_code == -1
        assert task.error is not None
        assert "Compact task failed: Unexpected error" in task.error
        assert task.completed_at is not None

    async def test_execute_compact_task_with_output_callback(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test compact task with output callback"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-pass",
        }

        async def mock_compact_with_callback(
            repository_path: str, passphrase: str, output_callback
        ) -> ProcessResult:
            output_callback("Compacting segments...")
            output_callback("Compacting complete")
            return ProcessResult(
                return_code=0, stdout=b"Compacting complete", stderr=b"", error=None
            )

        mock_job_executor.execute_compact_task = mock_compact_with_callback

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0
        assert len(task.output_lines) == 2
        assert "Compacting segments..." in task.output_lines
        assert "Compacting complete" in task.output_lines

    async def test_execute_compact_task_with_repository_params(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test compact task uses repository data over task parameters"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.COMPACT,
            task_name="Test Compact",
            parameters={
                "repository_path": "/tmp/wrong-repo",
                "passphrase": "wrong-pass",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/correct-repo",
            "passphrase": "correct-pass",
        }

        captured_path = None
        captured_passphrase = None

        async def mock_compact_capture_params(
            repository_path: str, passphrase: str, output_callback
        ) -> ProcessResult:
            nonlocal captured_path, captured_passphrase
            captured_path = repository_path
            captured_passphrase = passphrase
            return ProcessResult(
                return_code=0, stdout=b"Compacting complete", stderr=b"", error=None
            )

        mock_job_executor.execute_compact_task = mock_compact_capture_params

        success = await job_manager_with_mocks.compact_executor.execute_compact_task(
            job, task, 0
        )

        assert success is True
        assert captured_path == "/tmp/correct-repo"
        assert captured_passphrase == "correct-pass"
