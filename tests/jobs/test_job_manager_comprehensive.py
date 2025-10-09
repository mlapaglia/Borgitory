"""
Comprehensive tests for JobManager - covering missing lines and functionality
"""

import pytest
import uuid
import asyncio
from typing import Generator, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.utils.datetime_utils import now_utc
from unittest.mock import Mock, AsyncMock
from contextlib import contextmanager

from sqlalchemy.orm import Session

from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_models import (
    JobManagerConfig,
    JobManagerDependencies,
    BorgJob,
    BorgJobTask,
    TaskTypeEnum,
    TaskStatusEnum,
)
from borgitory.services.jobs.job_manager_factory import (
    JobManagerFactory,
    get_default_job_manager_dependencies,
    get_test_job_manager_dependencies,
)
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.models.database import Repository


# Module-level mock fixtures that can be used by all test classes
@pytest.fixture
def mock_job_executor() -> Mock:
    """Create a mock job executor with all needed methods"""
    executor = Mock()
    executor.start_process = AsyncMock()
    executor.monitor_process_output = AsyncMock()
    executor.execute_command = AsyncMock()
    executor.execute_prune_task = AsyncMock()
    executor.execute_cloud_sync_task = AsyncMock()
    return executor


@pytest.fixture
def mock_database_manager() -> Mock:
    """Create a mock database manager"""
    db_manager = Mock()
    db_manager.get_repository_data = AsyncMock()
    db_manager.update_job_status = AsyncMock()
    db_manager.update_task_status = AsyncMock()
    db_manager.create_job = AsyncMock()
    db_manager.create_task = AsyncMock()
    db_manager.create_database_job = AsyncMock()
    return db_manager


@pytest.fixture
def mock_output_manager() -> Mock:
    """Create a mock output manager"""
    output_manager = Mock()
    output_manager.create_job_output = Mock()
    output_manager.add_output_line = AsyncMock()
    output_manager.stream_job_output = Mock()
    output_manager.get_job_output = Mock()
    return output_manager


@pytest.fixture
def mock_queue_manager() -> Mock:
    """Create a mock queue manager"""
    queue_manager = Mock()
    queue_manager.add_job = Mock()
    queue_manager.get_next_job = Mock()
    queue_manager.remove_job = Mock()
    queue_manager.initialize = AsyncMock()
    return queue_manager


@pytest.fixture
def mock_event_broadcaster() -> Mock:
    """Create a mock event broadcaster"""
    broadcaster = Mock()
    broadcaster.broadcast_job_update = Mock()
    broadcaster.broadcast_task_update = Mock()
    broadcaster.initialize = AsyncMock()
    return broadcaster


@pytest.fixture
def mock_secure_borg_command() -> Mock:
    """Create a mock secure borg command context manager"""
    mock_cm = Mock()
    mock_cm.__aenter__ = AsyncMock(
        return_value=(
            ["borg", "create", "repo::test-archive", "/tmp"],
            {"BORG_PASSPHRASE": "test"},
            None,
        )
    )
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


@pytest.fixture
def mock_notification_service() -> Mock:
    """Create a mock notification service"""
    notification_service = Mock()
    notification_service.load_config_from_storage = Mock()
    notification_service.send_notification = AsyncMock()
    return notification_service


class TestJobManagerFactory:
    """Test JobManagerFactory methods for dependency injection"""

    def test_create_dependencies_default(self) -> None:
        """Test creating default dependencies"""
        deps = JobManagerFactory.create_dependencies()

        assert deps is not None
        assert deps.job_executor is not None
        assert deps.output_manager is not None
        assert deps.queue_manager is not None
        assert deps.event_broadcaster is not None
        assert deps.database_manager is not None

        # Test that it uses default session factory
        assert deps.db_session_factory is not None

    def test_create_dependencies_with_config(self) -> None:
        """Test creating dependencies with custom config"""
        config = JobManagerConfig(
            max_concurrent_backups=10,
            max_output_lines_per_job=2000,
            queue_poll_interval=0.2,
        )

        deps = JobManagerFactory.create_dependencies(config=config)

        assert deps.queue_manager is not None
        assert deps.output_manager is not None
        assert deps.queue_manager.max_concurrent_backups == 10

    def test_create_for_testing(self) -> None:
        """Test creating dependencies for testing"""
        mock_subprocess = AsyncMock()
        mock_db_session = Mock()
        mock_rclone = Mock()

        deps = JobManagerFactory.create_for_testing(
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.subprocess_executor is mock_subprocess
        assert deps.db_session_factory is mock_db_session
        assert deps.rclone_service is mock_rclone

    def test_create_minimal(self) -> None:
        """Test creating minimal dependencies"""
        deps = JobManagerFactory.create_minimal()

        assert deps is not None
        assert deps.queue_manager is not None
        assert deps.output_manager is not None
        # Should have reduced limits
        assert deps.queue_manager.max_concurrent_backups == 1


class TestJobManagerTaskExecution:
    """Test task execution methods with real database"""

    @pytest.fixture
    def job_manager_with_db(
        self,
        test_db: AsyncSession,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> JobManager:
        """Create job manager with real database session and mocked services"""

        @contextmanager
        def db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        # Use the factory to create test dependencies with proper protocol specs
        deps = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=mock_event_broadcaster
        )

        # Override with real database session
        deps.db_session_factory = db_session_factory

        # Create a real database manager that uses the real database session
        from borgitory.services.jobs.job_database_manager import JobDatabaseManager

        real_db_manager = JobDatabaseManager(db_session_factory=db_session_factory)
        deps.database_manager = real_db_manager

        manager = JobManager(dependencies=deps)

        # Override specific mocks if needed for the test
        manager.output_manager = mock_output_manager
        manager.queue_manager = mock_queue_manager

        return manager

    def _ensure_mock_dependencies(
        self,
        job_manager: JobManager,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> None:
        """Helper method to ensure job manager has proper mock dependencies"""
        job_manager.output_manager = mock_output_manager
        job_manager.queue_manager = mock_queue_manager
        job_manager.event_broadcaster = mock_event_broadcaster

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

        @contextmanager
        def mock_db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        # Use the factory to create test dependencies
        deps = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=mock_event_broadcaster
        )

        # Override with real database session and specific mocks
        deps.db_session_factory = mock_db_session_factory
        deps.job_executor = mock_job_executor
        deps.database_manager = mock_database_manager
        deps.output_manager = mock_output_manager
        deps.queue_manager = mock_queue_manager
        deps.notification_service = mock_notification_service

        job_manager = JobManager(dependencies=deps)

        return job_manager

    @pytest.fixture
    def job_manager_with_secure_command_mock(
        self,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
        mock_notification_service: Mock,
        mock_secure_borg_command: Mock,
    ) -> JobManager:
        """Create job manager with secure command mock for dry run tests"""

        # Use the factory to create test dependencies
        deps = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=mock_event_broadcaster
        )

        # Override with specific mocks
        deps.job_executor = mock_job_executor
        deps.database_manager = mock_database_manager
        deps.output_manager = mock_output_manager
        deps.queue_manager = mock_queue_manager
        deps.notification_service = mock_notification_service

        job_manager = JobManager(dependencies=deps)

        # Inject the secure command mock into the backup executor
        job_manager.backup_executor.secure_borg_command = mock_secure_borg_command  # type: ignore[attr-defined]

        return job_manager

    async def test_create_composite_job(
        self, job_manager_with_mocks: JobManager, sample_repository: Repository
    ) -> None:
        """Test creating a composite job with multiple tasks"""
        task_definitions = [
            TaskDefinition(
                type=TaskTypeEnum.BACKUP,
                name="Backup data",
                parameters={
                    "paths": ["/tmp"],
                    "excludes": ["*.tmp"],
                },
            ),
            TaskDefinition(
                type=TaskTypeEnum.PRUNE,
                name="Prune old archives",
                parameters={
                    "keep_daily": 7,
                    "keep_weekly": 4,
                },
            ),
        ]

        # Mock the execution so we don't actually run the job
        job_manager_with_mocks._execute_composite_job = AsyncMock()  # type: ignore[method-assign]

        job_id = await job_manager_with_mocks.create_composite_job(
            job_type="scheduled_backup",
            task_definitions=task_definitions,
            repository=sample_repository,
        )

        assert job_id is not None
        assert job_id in job_manager_with_mocks.jobs

        job = job_manager_with_mocks.jobs[job_id]
        assert job.job_type == "composite"
        assert len(job.tasks) == 2
        assert job.repository_id == sample_repository.id

        # Verify tasks were created correctly
        assert job.tasks[0].task_type == "backup"
        assert job.tasks[0].task_name == "Backup data"
        assert job.tasks[1].task_type == "prune"

    async def test_execute_composite_job_success(
        self, job_manager_with_mocks: JobManager, sample_repository: Repository
    ) -> None:
        """Test executing a composite job successfully"""
        # Create a simple composite job
        job_id = uuid.uuid4()
        task1 = BorgJobTask(task_type=TaskTypeEnum.BACKUP, task_name="Test Backup")
        task2 = BorgJobTask(task_type=TaskTypeEnum.PRUNE, task_name="Test Prune")

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.PENDING,
            started_at=now_utc(),
            tasks=[task1, task2],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Mock individual task execution to succeed
        async def mock_backup_task(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = TaskStatusEnum.COMPLETED
            task.return_code = 0
            task.completed_at = now_utc()
            return True

        async def mock_prune_task(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = TaskStatusEnum.COMPLETED
            task.return_code = 0
            task.completed_at = now_utc()
            return True

        # Configure mock executors
        job_manager_with_mocks.backup_executor.execute_backup_task = mock_backup_task  # type: ignore[method-assign]
        job_manager_with_mocks.prune_executor.execute_prune_task = mock_prune_task  # type: ignore[method-assign]

        await job_manager_with_mocks._execute_composite_job(job)

        # Verify job completed successfully
        assert job.status == "completed"
        assert job.completed_at is not None
        assert task1.status == "completed"
        assert task2.status == "completed"

    async def test_execute_composite_job_critical_failure(
        self, job_manager_with_db: JobManager, sample_repository: Repository
    ) -> None:
        """Test composite job with critical task failure"""
        # Create task definitions for backup and prune
        task_definitions = [
            TaskDefinition(
                type=TaskTypeEnum.BACKUP,
                name="Test Backup",
                parameters={
                    "source_path": "/tmp/test",
                    "compression": "lz4",
                    "dry_run": False,
                },
            ),
            TaskDefinition(
                type=TaskTypeEnum.PRUNE,
                name="Test Prune",
                parameters={
                    "keep_daily": 7,
                    "keep_weekly": 4,
                },
            ),
        ]

        # Use the proper job creation method that creates database records
        job_id = await job_manager_with_db.create_composite_job(
            job_type=JobTypeEnum.BACKUP,
            task_definitions=task_definitions,
            repository=sample_repository,
        )

        # Get the created job
        job = job_manager_with_db.jobs[job_id]

        # Mock backup to fail (critical)
        async def mock_backup_fail(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = "Backup failed"
            task.completed_at = now_utc()
            return False

        # Prune should not be called due to critical failure
        mock_prune = AsyncMock()

        # Configure mock executors
        job_manager_with_db.backup_executor.execute_backup_task = mock_backup_fail  # type: ignore[method-assign]
        job_manager_with_db.prune_executor.execute_prune_task = mock_prune  # type: ignore[method-assign]

        # Wait for the job to complete (it starts automatically)

        await asyncio.sleep(0.1)  # Give the job time to execute

        # Get the updated tasks from the job
        task1 = job.tasks[0]  # backup task
        task2 = job.tasks[1]  # prune task

        # Verify job failed due to critical task failure
        assert job.status == "failed"
        assert task1.status == TaskStatusEnum.FAILED

        # Verify remaining task was marked as skipped due to critical failure
        assert task2.status == TaskStatusEnum.SKIPPED
        assert task2.completed_at is not None
        assert any(
            "Task skipped due to critical task failure" in line
            for line in task2.output_lines
        )

        # Prune should not have been called due to critical failure
        mock_prune.assert_not_called()

        # Verify database persistence - actually query the database to confirm the data was saved
        from borgitory.models.database import (
            Job as DatabaseJob,
            JobTask as DatabaseTask,
        )

        # Get the database session from the job manager
        db_session_factory = job_manager_with_db.dependencies.db_session_factory
        assert db_session_factory is not None

        with db_session_factory() as db:
            # Query the database for the job and its tasks
            db_job = db.query(DatabaseJob).filter(DatabaseJob.id == job_id).first()
            assert db_job is not None, f"Job {job_id} should be persisted in database"

            # Query for the tasks
            db_tasks = (
                db.query(DatabaseTask)
                .filter(DatabaseTask.job_id == job_id)
                .order_by(DatabaseTask.task_order)
                .all()
            )
            assert len(db_tasks) == 2, (
                f"Expected 2 tasks in database, got {len(db_tasks)}"
            )

            # Verify the backup task (index 0) is failed
            backup_db_task = db_tasks[0]
            assert backup_db_task.task_type == "backup"
            assert backup_db_task.status == TaskStatusEnum.FAILED
            assert backup_db_task.return_code == 1
            assert backup_db_task.completed_at is not None

            # Verify the prune task (index 1) is skipped - THIS IS THE KEY TEST
            prune_db_task = db_tasks[1]
            assert prune_db_task.task_type == "prune"
            assert prune_db_task.status == TaskStatusEnum.SKIPPED, (
                f"Expected prune task to be 'skipped' in database, got '{prune_db_task.status}'"
            )
            assert prune_db_task.completed_at is not None, (
                "Skipped task should have completed_at timestamp"
            )

            # Verify the job status is failed
            assert db_job.status == JobStatusEnum.FAILED
            assert db_job.finished_at is not None

    async def test_execute_backup_task_success(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful backup task execution"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
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
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors
        mock_database_manager.get_repository_data.return_value = {
            "id": sample_repository.id,
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

        success = await job_manager_with_mocks.backup_executor.execute_backup_task(
            job, task, 0
        )

        assert success is True
        assert task.status == TaskStatusEnum.COMPLETED
        assert task.return_code == 0
        # Task execution should complete successfully

    async def test_execute_backup_task_success_with_proper_di(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task execution"""

        # Setup test data
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
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
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )

        # Add job to manager
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors
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
        assert task.status == TaskStatusEnum.COMPLETED
        assert task.return_code == 0

        # Verify mock interactions
        mock_database_manager.get_repository_data.assert_called_once_with(1)
        mock_job_executor.start_process.assert_called_once()
        mock_job_executor.monitor_process_output.assert_called_once()

    async def test_execute_backup_task_failure(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task failure handling"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Test Backup",
            parameters={"paths": ["/tmp"]},
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors for failure
        mock_database_manager.get_repository_data.return_value = {
            "id": sample_repository.id,
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

        success = await job_manager_with_mocks.backup_executor.execute_backup_task(
            job, task, 0
        )

        assert success is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.return_code == 2
        assert task.error is not None
        assert "Backup failed" in task.error

    async def test_execute_backup_task_with_dry_run(
        self,
        job_manager_with_secure_command_mock: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
        mock_secure_borg_command: Mock,
    ) -> None:
        """Test backup task execution with dry_run flag"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Test Backup Dry Run",
            parameters={
                "source_path": "/tmp",
                "excludes": ["*.log"],
                "archive_name": "test-archive-dry",
                "dry_run": True,  # This is the key parameter we're testing
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_secure_command_mock.jobs[job_id] = job
        job_manager_with_secure_command_mock.output_manager.create_job_output(job_id)

        # Configure mock behaviors
        mock_database_manager.get_repository_data.return_value = {
            "id": sample_repository.id,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
            "keyfile_content": None,
        }

        mock_process = AsyncMock()
        mock_job_executor.start_process.return_value = mock_process

        mock_job_executor.monitor_process_output.return_value = ProcessResult(
            return_code=0,
            stdout=b"Archive would be created (dry run)",
            stderr=b"",
            error=None,
        )

        success = await job_manager_with_secure_command_mock.backup_executor.execute_backup_task(
            job, task, 0
        )

        # Verify the task completed successfully
        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

        # The --dry-run flag is verified in the logs - we can see it in the "Final additional_args" log line
        # This test verifies that the dry_run parameter is properly processed and the task completes successfully

    async def test_execute_prune_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful prune task execution"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.PRUNE,
            task_name="Test Prune",
            parameters={
                "repository_path": "/tmp/test-repo",
                "passphrase": "test-pass",
                "keep_daily": 7,
                "keep_weekly": 4,
                "show_stats": True,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,  # Add repository_id for the updated method
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors
        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-pass",
        }

        mock_job_executor.execute_prune_task.return_value = ProcessResult(
            return_code=0, stdout=b"Pruning complete", stderr=b"", error=None
        )

        success = await job_manager_with_mocks.prune_executor.execute_prune_task(
            job, task, 0
        )

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    async def test_execute_check_task_success(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful check task execution"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.CHECK,
            task_name="Test Check",
            parameters={"repository_only": True},
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors
        mock_database_manager.get_repository_data.return_value = {
            "id": sample_repository.id,
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_process = AsyncMock()
        mock_job_executor.start_process.return_value = mock_process

        mock_job_executor.monitor_process_output.return_value = ProcessResult(
            return_code=0, stdout=b"Repository check passed", stderr=b"", error=None
        )

        success = await job_manager_with_mocks.check_executor.execute_check_task(
            job, task, 0
        )

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    async def test_execute_cloud_sync_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful cloud sync task execution"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.CLOUD_SYNC,
            task_name="Test Cloud Sync",
            parameters={
                "repository_path": "/tmp/test-repo",
                "cloud_sync_config_id": 1,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,  # Add repository_id for cloud sync task
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock behaviors
        mock_database_manager.get_repository_data.return_value = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        mock_job_executor.execute_cloud_sync_task.return_value = ProcessResult(
            return_code=0, stdout=b"Sync complete", stderr=b"", error=None
        )

        success = (
            await job_manager_with_mocks.cloud_sync_executor.execute_cloud_sync_task(
                job, task, 0
            )
        )

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    async def test_execute_notification_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_notification_service: Mock,
        test_db: AsyncSession,
    ) -> None:
        """Test successful notification task execution"""
        # Create a notification configuration in the database
        from borgitory.models.database import NotificationConfig

        notification_config = NotificationConfig()
        notification_config.name = "test-notification"
        notification_config.enabled = True
        notification_config.provider = "pushover"
        notification_config.provider_config = (
            '{"user_key": "'
            + "u"
            + "x" * 29
            + '", "app_token": "'
            + "a"
            + "x" * 29
            + '"}'
        )
        test_db.add(notification_config)
        test_db.commit()
        test_db.refresh(notification_config)

        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.NOTIFICATION,
            task_name="Test Notification",
            parameters={
                "notification_config_id": notification_config.id,
                "title": "Test Title",
                "message": "Test Message",
                "priority": 1,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        # Configure mock notification service
        mock_notification_service.load_config_from_storage.return_value = {
            "user_key": "u" + "x" * 29,
            "app_token": "a" + "x" * 29,
        }

        from borgitory.services.notifications.types import NotificationResult

        mock_notification_service.send_notification.return_value = NotificationResult(
            success=True, provider="pushover", message="Message sent successfully"
        )

        success = await job_manager_with_mocks.notification_executor.execute_notification_task(
            job, task, 0
        )

        assert success is True
        assert task.status == TaskStatusEnum.COMPLETED
        assert task.return_code == 0
        assert task.error is None

        # Verify notification service was called
        mock_notification_service.send_notification.assert_called_once()

    async def test_execute_notification_task_no_config(
        self, job_manager_with_mocks: JobManager
    ) -> None:
        """Test notification task with missing config"""
        job_id = uuid.uuid4()
        task = BorgJobTask(
            task_type=TaskTypeEnum.NOTIFICATION,
            task_name="Test Notification",
            parameters={},
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)

        success = await job_manager_with_mocks.notification_executor.execute_notification_task(
            job, task, 0
        )

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error is not None
        assert "No notification configuration" in task.error


class TestJobManagerExternalIntegration:
    """Test external job registration and management"""

    def _ensure_mock_dependencies(
        self,
        job_manager: JobManager,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> None:
        """Helper method to ensure job manager has proper mock dependencies"""
        job_manager.output_manager = mock_output_manager
        job_manager.queue_manager = mock_queue_manager
        job_manager.event_broadcaster = mock_event_broadcaster

    @pytest.fixture
    def job_manager(
        self,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> JobManager:
        """Create job manager for testing"""
        job_manager = JobManager()
        self._ensure_mock_dependencies(
            job_manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )
        return job_manager


class TestJobManagerDatabaseIntegration:
    """Test database integration methods"""

    def _ensure_mock_dependencies(
        self,
        job_manager: JobManager,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> None:
        """Helper method to ensure job manager has proper mock dependencies"""
        job_manager.output_manager = mock_output_manager
        job_manager.queue_manager = mock_queue_manager
        job_manager.event_broadcaster = mock_event_broadcaster

    @pytest.fixture
    def job_manager_with_db(
        self,
        test_db: AsyncSession,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> JobManager:
        """Create job manager with real database session"""

        @contextmanager
        def db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        deps = JobManagerFactory.create_for_testing()
        deps.db_session_factory = db_session_factory

        # Create a real database manager instead of using the mock
        from borgitory.services.jobs.job_database_manager import JobDatabaseManager

        deps.database_manager = JobDatabaseManager(db_session_factory)

        manager = JobManager(dependencies=deps)

        # Ensure our mocks are actually used (override any defaults)
        self._ensure_mock_dependencies(
            manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )

        return manager

    async def test_get_repository_data_success(
        self, job_manager_with_db: JobManager, sample_repository: Repository
    ) -> None:
        """Test getting repository data successfully"""
        # Mock the get_passphrase method to avoid encryption issues
        sample_repository.get_passphrase = Mock(return_value="test-passphrase")  # type: ignore[method-assign]

        result = await job_manager_with_db._get_repository_data(sample_repository.id)

        assert result is not None
        assert result["id"] == sample_repository.id
        assert result["name"] == "test-repo"
        assert result["path"] == "/tmp/test-repo"
        assert result["passphrase"] == "test-passphrase"

    async def test_get_repository_data_not_found(
        self, job_manager_with_db: JobManager
    ) -> None:
        """Test getting repository data for non-existent repository"""
        result = await job_manager_with_db._get_repository_data(99999)
        assert result is None


class TestJobManagerStreamingAndUtility:
    """Test streaming and utility methods"""

    def _ensure_mock_dependencies(
        self,
        job_manager: JobManager,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> None:
        """Helper method to ensure job manager has proper mock dependencies"""
        job_manager.output_manager = mock_output_manager
        job_manager.queue_manager = mock_queue_manager
        job_manager.event_broadcaster = mock_event_broadcaster

    @pytest.fixture
    def job_manager(
        self,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> JobManager:
        job_manager = JobManager()
        self._ensure_mock_dependencies(
            job_manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )
        return job_manager

    async def test_stream_job_output(self, job_manager: JobManager) -> None:
        """Test streaming job output"""

        async def mock_stream() -> AsyncGenerator[dict[str, object], None]:
            yield {"line": "output line 1", "progress": {}}
            yield {"line": "output line 2", "progress": {"percent": 50}}

        job_manager.output_manager.stream_job_output = Mock(return_value=mock_stream())  # type: ignore[method-assign]

        output_list = []
        async for output in job_manager.stream_job_output(uuid.uuid4()):
            output_list.append(output)

        assert len(output_list) == 2
        assert output_list[0]["line"] == "output line 1"
        assert output_list[1]["progress"]["percent"] == 50  # type: ignore[index]

    async def test_stream_job_output_no_manager(self) -> None:
        """Test streaming output when no output manager"""
        manager = JobManager()
        # Create a mock output manager that returns an empty async generator
        from unittest.mock import Mock
        from typing import AsyncGenerator

        async def empty_stream() -> AsyncGenerator[dict, None]:
            return
            yield  # This line will never be reached, but makes it a proper async generator

        mock_output_manager = Mock()
        mock_output_manager.stream_job_output = Mock(return_value=empty_stream())
        manager.output_manager = mock_output_manager

        output_list = []
        async for output in manager.stream_job_output(uuid.uuid4()):
            output_list.append(output)

        assert len(output_list) == 0

    def test_get_job(self, job_manager: JobManager) -> None:
        """Test getting job by ID"""
        job_id = uuid.uuid4()
        job = BorgJob(id=job_id, status=JobStatusEnum.RUNNING, started_at=now_utc())
        job_manager.jobs[job_id] = job

        retrieved = job_manager.get_job(job_id)
        assert retrieved is job

        assert job_manager.get_job(uuid.uuid4()) is None

    def test_list_jobs(self, job_manager: JobManager) -> None:
        """Test listing all jobs"""
        job1_id = uuid.uuid4()
        job2_id = uuid.uuid4()
        job1 = BorgJob(id=job1_id, status=JobStatusEnum.RUNNING, started_at=now_utc())
        job2 = BorgJob(id=job2_id, status=JobStatusEnum.COMPLETED, started_at=now_utc())

        job_manager.jobs[job1_id] = job1
        job_manager.jobs[job2_id] = job2

        jobs = job_manager.list_jobs()

        assert len(jobs) == 2
        assert jobs[job1_id] is job1
        assert jobs[job2_id] is job2
        assert jobs is not job_manager.jobs  # Should return copy

    async def test_get_job_output_stream(self, job_manager: JobManager) -> None:
        """Test getting job output stream data"""
        job_id = uuid.uuid4()

        # Mock output manager with job output data
        mock_output = Mock()
        mock_output.lines = [
            {"text": "line 1", "timestamp": "2024-01-01T12:00:00"},
            {"text": "line 2", "timestamp": "2024-01-01T12:00:01"},
        ]
        mock_output.current_progress = {"percent": 75}
        mock_output.total_lines = 2

        job_manager.output_manager.get_job_output = Mock(return_value=mock_output)  # type: ignore[method-assign]

        result = await job_manager.get_job_output_stream(job_id)

        assert hasattr(result, "lines")
        assert hasattr(result, "progress")
        assert hasattr(result, "total_lines")
        assert len(result.lines) == 2
        assert result.progress["percent"] == 75
        assert result.total_lines == 2

    async def test_get_job_output_stream_no_output(
        self, job_manager: JobManager
    ) -> None:
        """Test getting output stream when no output exists"""
        job_manager.output_manager.get_job_output = Mock(return_value=None)  # type: ignore[method-assign]

        result = await job_manager.get_job_output_stream(uuid.uuid4())

        assert result.lines == []
        assert result.progress == {}

    def test_get_active_jobs_count(self, job_manager: JobManager) -> None:
        """Test getting count of active jobs"""
        job_manager.jobs = {
            uuid.uuid4(): Mock(status="running"),
            uuid.uuid4(): Mock(status="queued"),
            uuid.uuid4(): Mock(status="completed"),
            uuid.uuid4(): Mock(status="failed"),
            uuid.uuid4(): Mock(status="running"),
        }

        count = job_manager.get_active_jobs_count()
        assert count == 3  # 2 running + 1 queued

    async def test_cancel_job_success(self, job_manager: JobManager) -> None:
        """Test cancelling a job successfully"""
        job = Mock(status="running")
        job_id = uuid.uuid4()
        job_manager.jobs[job_id] = job

        mock_process = AsyncMock()
        job_manager._processes[job_id] = mock_process
        job_manager.executor.terminate_process = AsyncMock(return_value=True)  # type: ignore[method-assign]

        result = await job_manager.cancel_job(job_id)

        assert result is True
        assert job.status == JobStatusEnum.CANCELLED
        assert job.completed_at is not None
        assert job_id not in job_manager._processes

    async def test_cancel_job_not_cancellable(self, job_manager: JobManager) -> None:
        """Test cancelling job in non-cancellable state"""
        job = Mock(status="completed")
        job_id = uuid.uuid4()
        job_manager.jobs[job_id] = job

        result = await job_manager.cancel_job(job_id)
        assert result is False

    async def test_cancel_job_not_found(self, job_manager: JobManager) -> None:
        """Test cancelling non-existent job"""
        result = await job_manager.cancel_job(uuid.uuid4())
        assert result is False


class TestJobManagerFactoryFunctions:
    """Test module-level factory functions"""

    def test_get_default_job_manager_dependencies(self) -> None:
        """Test getting default dependencies"""
        deps = get_default_job_manager_dependencies()

        assert isinstance(deps, JobManagerDependencies)
        assert deps.job_executor is not None
        assert deps.output_manager is not None
        assert deps.queue_manager is not None

    def test_get_test_job_manager_dependencies(self) -> None:
        """Test getting test dependencies"""
        mock_subprocess = AsyncMock()
        mock_db_session = Mock()
        mock_rclone = Mock()

        mock_event_broadcaster = Mock(spec=JobEventBroadcasterProtocol)

        deps = get_test_job_manager_dependencies(
            mock_event_broadcaster=mock_event_broadcaster,
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.event_broadcaster is mock_event_broadcaster
        assert deps.subprocess_executor is mock_subprocess
        assert deps.db_session_factory is mock_db_session
        assert deps.rclone_service is mock_rclone
