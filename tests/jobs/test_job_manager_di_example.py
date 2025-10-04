"""
Example of how to use proper DI in tests instead of patches
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock

from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_models import (
    JobManagerConfig,
    JobManagerDependencies,
    BorgJob,
    BorgJobTask,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.utils.datetime_utils import now_utc


class TestJobManagerWithProperDI:
    """Example of using proper DI instead of patches"""

    @pytest.fixture
    def mock_job_executor(self) -> Mock:
        """Create a mock job executor with all needed methods"""
        executor = Mock()
        executor.start_process = AsyncMock()
        executor.monitor_process_output = AsyncMock()
        executor.execute_command = AsyncMock()
        executor.execute_prune_task = AsyncMock()
        executor.execute_cloud_sync_task = AsyncMock()
        return executor

    @pytest.fixture
    def mock_output_manager(self) -> Mock:
        """Create a mock output manager"""
        output_manager = Mock()
        output_manager.create_job_output = Mock()
        output_manager.add_output_line = Mock()
        return output_manager

    @pytest.fixture
    def mock_database_manager(self) -> Mock:
        """Create a mock database manager"""
        db_manager = Mock()
        db_manager.get_repository_data = AsyncMock()
        return db_manager

    @pytest.fixture
    def job_manager_with_mocks(
        self,
        mock_job_executor: Mock,
        mock_output_manager: Mock,
        mock_database_manager: Mock,
    ) -> JobManager:
        """Create job manager with injected mock dependencies"""

        # Create custom dependencies with mocks
        custom_deps = JobManagerDependencies(
            job_executor=mock_job_executor,
            output_manager=mock_output_manager,
            database_manager=mock_database_manager,
        )

        # Create full dependencies with our mocks injected
        full_deps = JobManagerFactory.create_dependencies(
            config=JobManagerConfig(), custom_dependencies=custom_deps
        )

        # Create job manager with mock dependencies
        return JobManager(dependencies=full_deps)

    @pytest.mark.asyncio
    async def test_backup_task_success_with_di(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task execution using proper DI - no patches needed!"""

        # Setup test data
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="backup",
            task_name="Test Backup",
            parameters={
                "paths": ["/tmp"],
                "excludes": ["*.log"],
                "archive_name": "test-archive",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )

        # Add job to manager
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors - no patches needed!
        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_job_executor.start_process.return_value = mock_process

        mock_job_executor.monitor_process_output.return_value = ProcessResult(
            return_code=0,
            stdout=b"Archive created successfully",
            stderr=b"",
            error=None,
        )

        # Execute the task - the job manager will use our injected mocks
        success = await job_manager_with_mocks.backup_executor.execute_backup_task(
            job, task, 0
        )

        # Verify results
        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

        # Verify mock interactions
        mock_database_manager.get_repository_data.assert_called_once_with(1)
        mock_job_executor.start_process.assert_called_once()
        mock_job_executor.monitor_process_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_backup_task_failure_with_di(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task failure using proper DI"""

        # Setup test data
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="backup",
            task_name="Test Backup",
            parameters={
                "paths": ["/tmp"],
                "archive_name": "test-archive",
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )

        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mocks for failure scenario
        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_process = AsyncMock()
        mock_job_executor.start_process.return_value = mock_process

        mock_job_executor.monitor_process_output.return_value = ProcessResult(
            return_code=2,
            stdout=b"Repository locked",
            stderr=b"",
            error="Backup failed",
        )

        # Execute the task
        success = await job_manager_with_mocks.backup_executor.execute_backup_task(
            job, task, 0
        )

        # Verify failure
        assert success is False
        assert task.status == "failed"
        assert task.return_code == 2
        assert "Backup failed" in task.error

    @pytest.mark.asyncio
    async def test_prune_task_with_di(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test prune task using proper DI"""

        # Setup test data
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="prune",
            task_name="Test Prune",
            parameters={
                "keep_daily": 7,
                "keep_weekly": 4,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )

        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mocks
        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_job_executor.execute_prune_task.return_value = ProcessResult(
            return_code=0,
            stdout=b"Pruning complete",
            stderr=b"",
            error=None,
        )

        # Execute the task
        success = await job_manager_with_mocks.prune_executor.execute_prune_task(
            job, task, 0
        )

        # Verify results
        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

        # Verify mock interactions
        mock_database_manager.get_repository_data.assert_called_once_with(1)
        mock_job_executor.execute_prune_task.assert_called_once()
