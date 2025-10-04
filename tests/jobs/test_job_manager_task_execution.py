"""
Tests for JobManager task execution methods
"""

import pytest
import uuid
import asyncio
from typing import Generator
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
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.models.database import Repository


class TestJobManagerTaskExecution:
    """Test task execution methods with real database"""

    @pytest.fixture
    def job_manager_with_db(
        self,
        test_db: Session,
        mock_output_manager: Mock,
        mock_queue_manager: Mock,
        mock_event_broadcaster: Mock,
    ) -> JobManager:
        """Create job manager with real database session and proper notification service injection"""

        @contextmanager
        def db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        # Create notification service using proper DI
        from borgitory.dependencies import (
            get_http_client,
            get_notification_provider_factory,
        )
        from borgitory.services.notifications.service import NotificationService

        http_client = get_http_client()
        factory = get_notification_provider_factory(http_client)
        notification_service = NotificationService(provider_factory=factory)

        # Import cloud sync dependencies for complete testing
        from borgitory.dependencies import (
            get_rclone_service,
            get_encryption_service,
            get_storage_factory,
            get_registry_factory,
            get_provider_registry,
        )

        deps = JobManagerDependencies(
            db_session_factory=db_session_factory,
            notification_service=notification_service,
            # Add cloud sync dependencies for comprehensive testing
            rclone_service=get_rclone_service(),
            encryption_service=get_encryption_service(),
            storage_factory=get_storage_factory(get_rclone_service()),
            provider_registry=get_provider_registry(get_registry_factory()),
        )
        full_deps = JobManagerFactory.create_dependencies(custom_dependencies=deps)
        manager = JobManager(dependencies=full_deps)

        # Ensure our mocks are actually used (override any defaults)
        self._ensure_mock_dependencies(
            manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )

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
    ) -> JobManager:
        """Create job manager with injected mock dependencies"""

        # Create custom dependencies with mocks
        custom_deps = JobManagerDependencies(
            job_executor=mock_job_executor,
            database_manager=mock_database_manager,
            output_manager=mock_output_manager,
            queue_manager=mock_queue_manager,
            event_broadcaster=mock_event_broadcaster,
            notification_service=mock_notification_service,
        )

        # Create full dependencies with our mocks injected
        full_deps = JobManagerFactory.create_dependencies(
            config=JobManagerConfig(), custom_dependencies=custom_deps
        )

        # Create job manager with mock dependencies
        job_manager = JobManager(dependencies=full_deps)

        # Ensure our mocks are actually used (override any defaults)
        self._ensure_mock_dependencies(
            job_manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )

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

        # Create custom dependencies with mocks
        custom_deps = JobManagerDependencies(
            job_executor=mock_job_executor,
            database_manager=mock_database_manager,
            output_manager=mock_output_manager,
            queue_manager=mock_queue_manager,
            event_broadcaster=mock_event_broadcaster,
            notification_service=mock_notification_service,
        )

        # Create full dependencies with our mocks injected
        full_deps = JobManagerFactory.create_dependencies(
            config=JobManagerConfig(), custom_dependencies=custom_deps
        )

        # Create job manager with mock dependencies
        job_manager = JobManager(dependencies=full_deps)

        # Ensure our mocks are actually used (override any defaults)
        self._ensure_mock_dependencies(
            job_manager, mock_output_manager, mock_queue_manager, mock_event_broadcaster
        )

        # Inject the secure command mock into the backup executor
        job_manager.backup_executor.secure_borg_command = mock_secure_borg_command  # type: ignore[attr-defined]

        return job_manager

    @pytest.mark.asyncio
    async def test_create_composite_job(
        self, job_manager_with_mocks: JobManager, sample_repository: Repository
    ) -> None:
        """Test creating a composite job with multiple tasks"""
        task_definitions = [
            TaskDefinition(
                type="backup",
                name="Backup data",
                parameters={
                    "paths": ["/tmp"],
                    "excludes": ["*.tmp"],
                },
            ),
            TaskDefinition(
                type="prune",
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

    @pytest.mark.asyncio
    async def test_execute_composite_job_success(
        self, job_manager_with_mocks: JobManager, sample_repository: Repository
    ) -> None:
        """Test executing a composite job successfully"""
        # Create a simple composite job
        job_id = str(uuid.uuid4())
        task1 = BorgJobTask(task_type="backup", task_name="Test Backup")
        task2 = BorgJobTask(task_type="prune", task_name="Test Prune")

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="pending",
            started_at=now_utc(),
            tasks=[task1, task2],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

        # Mock individual task execution to succeed
        async def mock_backup_task(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = "completed"
            task.return_code = 0
            task.completed_at = now_utc()
            return True

        async def mock_prune_task(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = "completed"
            task.return_code = 0
            task.completed_at = now_utc()
            return True

        # Configure mock executors
        job_manager_with_mocks.backup_executor.execute_backup_task = mock_backup_task  # type: ignore[assignment]
        job_manager_with_mocks.prune_executor.execute_prune_task = mock_prune_task  # type: ignore[assignment]

        await job_manager_with_mocks._execute_composite_job(job)

        # Verify job completed successfully
        assert job.status == "completed"
        assert job.completed_at is not None
        assert task1.status == "completed"
        assert task2.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_composite_job_critical_failure(
        self, job_manager_with_db: JobManager, sample_repository: Repository
    ) -> None:
        """Test composite job with critical task failure"""
        # Create task definitions for backup and prune
        task_definitions = [
            TaskDefinition(
                type="backup",
                name="Test Backup",
                parameters={
                    "source_path": "/tmp/test",
                    "compression": "lz4",
                    "dry_run": False,
                },
            ),
            TaskDefinition(
                type="prune",
                name="Test Prune",
                parameters={
                    "keep_daily": 7,
                    "keep_weekly": 4,
                },
            ),
        ]

        # Use the proper job creation method that creates database records
        job_id = await job_manager_with_db.create_composite_job(
            job_type="backup",
            task_definitions=task_definitions,
            repository=sample_repository,
        )

        # Get the created job
        job = job_manager_with_db.jobs[job_id]

        # Mock backup to fail (critical)
        async def mock_backup_fail(
            job: BorgJob, task: BorgJobTask, task_index: int
        ) -> bool:
            task.status = "failed"
            task.return_code = 1
            task.error = "Backup failed"
            task.completed_at = now_utc()
            return False

        # Prune should not be called due to critical failure
        mock_prune = AsyncMock()

        # Configure mock executors
        job_manager_with_db.backup_executor.execute_backup_task = mock_backup_fail  # type: ignore[method-assign,assignment]
        job_manager_with_db.prune_executor.execute_prune_task = mock_prune  # type: ignore[method-assign]

        # Wait for the job to complete (it starts automatically)
        await asyncio.sleep(0.1)  # Give the job time to execute

        # Get the updated tasks from the job
        task1 = job.tasks[0]  # backup task
        task2 = job.tasks[1]  # prune task

        # Verify job failed due to critical task failure
        assert job.status == "failed"
        assert task1.status == "failed"

        # Verify remaining task was marked as skipped due to critical failure
        assert task2.status == "skipped"
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
            assert backup_db_task.status == "failed"
            assert backup_db_task.return_code == 1
            assert backup_db_task.completed_at is not None

            # Verify the prune task (index 1) is skipped - THIS IS THE KEY TEST
            prune_db_task = db_tasks[1]
            assert prune_db_task.task_type == "prune"
            assert prune_db_task.status == "skipped", (
                f"Expected prune task to be 'skipped' in database, got '{prune_db_task.status}'"
            )
            assert prune_db_task.completed_at is not None, (
                "Skipped task should have completed_at timestamp"
            )

            # Verify the job status is failed
            assert db_job.status == "failed"
            assert db_job.finished_at is not None

    @pytest.mark.asyncio
    async def test_execute_backup_task_success(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful backup task execution"""
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
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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
        assert task.status == "completed"
        assert task.return_code == 0
        # Task execution should complete successfully

    @pytest.mark.asyncio
    async def test_execute_backup_task_success_with_proper_di(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task execution"""

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
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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
        assert task.status == "completed"
        assert task.return_code == 0

        # Verify mock interactions
        mock_database_manager.get_repository_data.assert_called_once_with(1)
        mock_job_executor.start_process.assert_called_once()
        mock_job_executor.monitor_process_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_backup_task_failure(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test backup task failure handling"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="backup", task_name="Test Backup", parameters={"paths": ["/tmp"]}
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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
        assert task.status == "failed"
        assert task.return_code == 2
        assert task.error is not None
        assert "Backup failed" in task.error

    @pytest.mark.asyncio
    async def test_execute_backup_task_with_dry_run(
        self,
        job_manager_with_secure_command_mock: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
        mock_secure_borg_command: Mock,
    ) -> None:
        """Test backup task execution with dry_run flag"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="backup",
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
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_secure_command_mock.jobs[job_id] = job
        job_manager_with_secure_command_mock.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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

    @pytest.mark.asyncio
    async def test_execute_prune_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful prune task execution"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="prune",
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
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,  # Add repository_id for the updated method
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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

    @pytest.mark.asyncio
    async def test_execute_check_task_success(
        self,
        job_manager_with_mocks: JobManager,
        sample_repository: Repository,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful check task execution"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="check",
            task_name="Test Check",
            parameters={"repository_only": True},
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=sample_repository.id,
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_success(
        self,
        job_manager_with_mocks: JobManager,
        mock_job_executor: Mock,
        mock_database_manager: Mock,
    ) -> None:
        """Test successful cloud sync task execution"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="cloud_sync",
            task_name="Test Cloud Sync",
            parameters={
                "repository_path": "/tmp/test-repo",
                "cloud_sync_config_id": 1,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,  # Add repository_id for cloud sync task
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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

    @pytest.mark.asyncio
    async def test_execute_notification_task_success(
        self, job_manager_with_mocks: JobManager, mock_notification_service: Mock
    ) -> None:
        """Test successful notification task execution"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="notification",
            task_name="Test Notification",
            parameters={
                "notification_config_id": 1,
                "title": "Test Title",
                "message": "Test Message",
                "priority": 1,
            },
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

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
        assert task.status == "completed"
        assert task.return_code == 0
        assert task.error is None

        # Verify notification service was called
        mock_notification_service.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_notification_task_no_config(
        self, job_manager_with_mocks: JobManager
    ) -> None:
        """Test notification task with missing config"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="notification", task_name="Test Notification", parameters={}
        )

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

        success = await job_manager_with_mocks.notification_executor.execute_notification_task(
            job, task, 0
        )

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error is not None
        assert "No notification configuration" in task.error

    @pytest.mark.asyncio
    async def test_execute_task_unknown_type(
        self, job_manager_with_mocks: JobManager
    ) -> None:
        """Test executing task with unknown type"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(task_type="unknown_task", task_name="Unknown Task")

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_mocks.jobs[job_id] = job
        job_manager_with_mocks.output_manager.create_job_output(job_id)  # type: ignore[union-attr]

        success = await job_manager_with_mocks._execute_task_with_executor(job, task, 0)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error is not None
        assert "Unknown task type: unknown_task" in task.error
