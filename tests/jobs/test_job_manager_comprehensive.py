"""
Comprehensive tests for JobManager - covering missing lines and functionality
"""

import pytest
import uuid
import asyncio
from typing import Generator, Dict, Any, AsyncGenerator
from borgitory.utils.datetime_utils import now_utc
from unittest.mock import Mock, AsyncMock, patch
from contextlib import contextmanager

from sqlalchemy.orm import Session

from borgitory.services.jobs.job_manager import (
    JobManager,
    JobManagerConfig,
    JobManagerDependencies,
    JobManagerFactory,
    BorgJob,
    BorgJobTask,
    get_default_job_manager_dependencies,
    get_test_job_manager_dependencies,
)
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.models.database import NotificationConfig, Repository


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
        assert deps.output_manager.max_lines_per_job == 2000

    def test_create_dependencies_with_custom_dependencies(self) -> None:
        """Test creating dependencies with partial custom dependencies"""
        mock_executor = Mock()
        mock_output_manager = Mock()

        custom_deps = JobManagerDependencies(
            job_executor=mock_executor,
            output_manager=mock_output_manager,
        )

        deps = JobManagerFactory.create_dependencies(custom_dependencies=custom_deps)

        # Custom dependencies should be preserved
        assert deps.job_executor is mock_executor
        assert deps.output_manager is mock_output_manager
        # Others should be created
        assert deps.queue_manager is not None
        assert deps.event_broadcaster is not None

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
        assert deps.output_manager.max_lines_per_job == 100

    def test_dependencies_post_init(self) -> None:
        """Test JobManagerDependencies post_init method"""
        # Test with no session factory
        deps = JobManagerDependencies()
        deps.__post_init__()

        assert deps.db_session_factory is not None

        # Test with custom session factory
        custom_factory = Mock()
        deps_custom = JobManagerDependencies(db_session_factory=custom_factory)
        deps_custom.__post_init__()

        assert deps_custom.db_session_factory is custom_factory


class TestJobManagerTaskExecution:
    """Test task execution methods with real database"""

    @pytest.fixture
    def job_manager_with_db(self, test_db: Session) -> JobManager:
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
        return manager

    @pytest.mark.asyncio
    async def test_create_composite_job(
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        with patch.object(
            job_manager_with_db, "_execute_composite_job", new=AsyncMock()
        ):
            job_id = await job_manager_with_db.create_composite_job(
                job_type="scheduled_backup",
                task_definitions=task_definitions,
                repository=sample_repository,
            )

        assert job_id is not None
        assert job_id in job_manager_with_db.jobs

        job = job_manager_with_db.jobs[job_id]
        assert job.job_type == "composite"
        assert len(job.tasks) == 2
        assert job.repository_id == sample_repository.id

        # Verify tasks were created correctly
        assert job.tasks[0].task_type == "backup"
        assert job.tasks[0].task_name == "Backup data"
        assert job.tasks[1].task_type == "prune"

    @pytest.mark.asyncio
    async def test_execute_composite_job_success(
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

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

        with patch.object(
            job_manager_with_db, "_execute_backup_task", side_effect=mock_backup_task
        ), patch.object(
            job_manager_with_db, "_execute_prune_task", side_effect=mock_prune_task
        ):
            await job_manager_with_db._execute_composite_job(job)

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

        with patch.object(
            job_manager_with_db, "_execute_backup_task", side_effect=mock_backup_fail
        ), patch.object(job_manager_with_db, "_execute_prune_task", mock_prune):
            # Wait for the job to complete (it starts automatically)
            import asyncio

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
        from src.borgitory.models.database import (
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
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock process execution and repository data
        mock_process = AsyncMock()
        result = ProcessResult(
            return_code=0,
            stdout=b"Archive created successfully",
            stderr=b"",
            error=None,
        )

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build, patch.object(
            job_manager_with_db.executor, "start_process", return_value=mock_process
        ), patch.object(
            job_manager_with_db.executor, "monitor_process_output", return_value=result
        ), patch.object(
            job_manager_with_db,
            "_get_repository_data",
            return_value={
                "id": sample_repository.id,
                "path": "/tmp/test-repo",
                "passphrase": "test-passphrase",
            },
        ):
            mock_build.return_value = (
                ["borg", "create", "repo::test-archive", "/tmp"],
                {"BORG_PASSPHRASE": "test"},
            )

            success = await job_manager_with_db._execute_backup_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0
        # Task execution should complete successfully

    @pytest.mark.asyncio
    async def test_execute_backup_task_failure(
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock failed process and repository data
        mock_process = AsyncMock()
        result = ProcessResult(
            return_code=2,
            stdout=b"Repository locked",
            stderr=b"",
            error="Backup failed",
        )

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build, patch.object(
            job_manager_with_db.executor, "start_process", return_value=mock_process
        ), patch.object(
            job_manager_with_db.executor, "monitor_process_output", return_value=result
        ), patch.object(
            job_manager_with_db,
            "_get_repository_data",
            return_value={
                "id": sample_repository.id,
                "path": "/tmp/test-repo",
                "passphrase": "test-passphrase",
            },
        ):
            mock_build.return_value = (
                ["borg", "create", "repo::archive"],
                {"BORG_PASSPHRASE": "test"},
            )

            success = await job_manager_with_db._execute_backup_task(job, task)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 2
        assert task.error is not None
        assert "Backup failed" in task.error

    @pytest.mark.asyncio
    async def test_execute_backup_task_with_dry_run(
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock process execution and repository data
        mock_process = AsyncMock()
        result = ProcessResult(
            return_code=0,
            stdout=b"Archive would be created (dry run)",
            stderr=b"",
            error=None,
        )

        # Capture the actual command built to verify --dry-run flag is included
        captured_command = None

        def mock_secure_borg_command(*args, **kwargs):
            nonlocal captured_command
            # Extract the arguments to build the command
            base_command = kwargs.get("base_command", args[0] if args else "")
            additional_args = kwargs.get("additional_args", [])
            captured_command = [base_command] + (additional_args or [])

            # Mock the context manager behavior
            class MockContextManager:
                async def __aenter__(self):
                    return (captured_command, {"BORG_PASSPHRASE": "test"}, None)

                async def __aexit__(self, *args):
                    pass

            return MockContextManager()

        with patch(
            "borgitory.services.jobs.job_manager.secure_borg_command",
            side_effect=mock_secure_borg_command,
        ), patch.object(
            job_manager_with_db.executor, "start_process", return_value=mock_process
        ), patch.object(
            job_manager_with_db.executor, "monitor_process_output", return_value=result
        ), patch.object(
            job_manager_with_db,
            "_get_repository_data",
            return_value={
                "id": sample_repository.id,
                "path": "/tmp/test-repo",
                "passphrase": "test-passphrase",
                "keyfile_content": None,
            },
        ):
            success = await job_manager_with_db._execute_backup_task(job, task)

        # Verify the task completed successfully
        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

        # Verify that the --dry-run flag was included in the command
        assert captured_command is not None
        assert "--dry-run" in captured_command, (
            f"Expected --dry-run in command: {captured_command}"
        )

    @pytest.mark.asyncio
    async def test_execute_prune_task_success(
        self, job_manager_with_db: JobManager
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock repository data
        mock_repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-pass",
        }

        # Mock successful prune
        result = ProcessResult(
            return_code=0, stdout=b"Pruning complete", stderr=b"", error=None
        )

        with patch.object(
            job_manager_with_db.executor, "execute_prune_task", return_value=result
        ), patch.object(
            job_manager_with_db, "_get_repository_data", return_value=mock_repo_data
        ):
            success = await job_manager_with_db._execute_prune_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    @pytest.mark.asyncio
    async def test_execute_check_task_success(
        self, job_manager_with_db: JobManager, sample_repository: Repository
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock successful check and repository data
        mock_process = AsyncMock()
        result = ProcessResult(
            return_code=0, stdout=b"Repository check passed", stderr=b"", error=None
        )

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build, patch.object(
            job_manager_with_db.executor, "start_process", return_value=mock_process
        ), patch.object(
            job_manager_with_db.executor, "monitor_process_output", return_value=result
        ), patch.object(
            job_manager_with_db,
            "_get_repository_data",
            return_value={
                "id": sample_repository.id,
                "path": "/tmp/test-repo",
                "passphrase": "test-passphrase",
            },
        ):
            mock_build.return_value = (
                ["borg", "check", "--repository-only"],
                {"BORG_PASSPHRASE": "test"},
            )

            success = await job_manager_with_db._execute_check_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_success(
        self, job_manager_with_db: JobManager
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock successful cloud sync
        result = ProcessResult(
            return_code=0, stdout=b"Sync complete", stderr=b"", error=None
        )

        # Mock repository data
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/tmp/test-repo",
            "passphrase": "test-passphrase",
        }

        with patch.object(
            job_manager_with_db.executor, "execute_cloud_sync_task", return_value=result
        ), patch.object(
            job_manager_with_db, "_get_repository_data", return_value=repo_data
        ):
            success = await job_manager_with_db._execute_cloud_sync_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0

    @pytest.mark.asyncio
    async def test_execute_notification_task_success(
        self, job_manager_with_db: JobManager, test_db: Session
    ) -> None:
        """Test successful notification task execution"""
        # Create notification config in database using new model
        notification_config = NotificationConfig()
        notification_config.name = "Test Pushover"
        notification_config.provider = "pushover"
        notification_config.enabled = True

        # Use the new NotificationService to prepare config for storage
        from borgitory.dependencies import (
            get_http_client,
            get_notification_provider_factory,
        )
        from borgitory.services.notifications.service import NotificationService

        # Manually resolve the dependency chain for testing
        http_client = get_http_client()
        factory = get_notification_provider_factory(http_client)
        notification_service = NotificationService(provider_factory=factory)
        notification_config.provider_config = (
            notification_service.prepare_config_for_storage(
                "pushover",
                {
                    "user_key": "u" + "x" * 29,  # 30 character user key
                    "app_token": "a" + "x" * 29,  # 30 character app token
                },
            )
        )

        test_db.add(notification_config)
        test_db.commit()
        test_db.refresh(notification_config)

        job_id = str(uuid.uuid4())
        task = BorgJobTask(
            task_type="notification",
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
            status="running",
            started_at=now_utc(),
            tasks=[task],
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock successful notification with proper database access
        with patch(
            "borgitory.services.jobs.job_manager.get_db_session"
        ) as mock_get_db, patch(
            "borgitory.services.notifications.service.NotificationService.send_notification"
        ) as mock_send:
            # Set up the database session context manager
            mock_get_db.return_value.__enter__.return_value = test_db

            # Mock successful notification result
            from borgitory.services.notifications.types import NotificationResult

            mock_result = NotificationResult(
                success=True, provider="pushover", message="Message sent successfully"
            )
            mock_send.return_value = mock_result

            success = await job_manager_with_db._execute_notification_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0
        assert task.error is None

        # Verify notification service was called
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_notification_task_no_config(
        self, job_manager_with_db: JobManager
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        success = await job_manager_with_db._execute_notification_task(job, task)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error is not None
        assert "No notification configuration" in task.error

    @pytest.mark.asyncio
    async def test_execute_task_unknown_type(
        self, job_manager_with_db: JobManager
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
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        success = await job_manager_with_db._execute_task(job, task)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error is not None
        assert "Unknown task type: unknown_task" in task.error


class TestJobManagerExternalIntegration:
    """Test external job registration and management"""

    @pytest.fixture
    def job_manager(self) -> JobManager:
        """Create job manager for testing"""
        return JobManager()

    def test_register_external_job(self, job_manager: JobManager) -> None:
        """Test registering an external job"""
        job_id = "external-job-123"

        job_manager.register_external_job(
            job_id, job_type="backup", job_name="External Backup"
        )

        assert job_id in job_manager.jobs
        job = job_manager.jobs[job_id]

        assert job.id == job_id
        assert job.job_type == "composite"
        assert job.status == "running"
        assert len(job.tasks) == 1
        assert job.tasks[0].task_type == "backup"
        assert job.tasks[0].task_name == "External Backup"
        assert job.tasks[0].status == "running"

    def test_update_external_job_status(self, job_manager: JobManager) -> None:
        """Test updating external job status"""
        job_id = "external-job-456"
        job_manager.register_external_job(job_id, job_type="backup")

        job_manager.update_external_job_status(job_id, "completed", return_code=0)

        job = job_manager.jobs[job_id]
        assert job.status == "completed"
        assert job.return_code == 0
        assert job.completed_at is not None

        # Main task should also be updated
        assert job.tasks[0].status == "completed"
        assert job.tasks[0].return_code == 0
        assert job.tasks[0].completed_at is not None

    def test_update_external_job_status_with_error(
        self, job_manager: JobManager
    ) -> None:
        """Test updating external job with error"""
        job_id = "external-job-error"
        job_manager.register_external_job(job_id, job_type="backup")

        job_manager.update_external_job_status(
            job_id, "failed", error="Backup failed", return_code=1
        )

        job = job_manager.jobs[job_id]
        assert job.status == "failed"
        assert job.error == "Backup failed"
        assert job.return_code == 1

        # Main task should also be updated
        assert job.tasks[0].status == "failed"
        assert job.tasks[0].error == "Backup failed"
        assert job.tasks[0].return_code == 1

    def test_update_external_job_status_not_registered(
        self, job_manager: JobManager
    ) -> None:
        """Test updating status for non-registered job"""
        # Should not raise error
        job_manager.update_external_job_status("nonexistent", "completed")
        assert "nonexistent" not in job_manager.jobs

    @pytest.mark.asyncio
    async def test_add_external_job_output(self, job_manager: JobManager) -> None:
        """Test adding output to external job"""
        job_id = "external-job-output"
        job_manager.register_external_job(job_id, job_type="backup")

        job_manager.add_external_job_output(job_id, "Backup progress: 50%")
        job_manager.add_external_job_output(job_id, "Backup completed")

        # Wait for async tasks
        await asyncio.sleep(0.01)

        job = job_manager.jobs[job_id]
        main_task = job.tasks[0]

        assert len(main_task.output_lines) == 2
        assert main_task.output_lines[0]["text"] == "Backup progress: 50%"
        assert main_task.output_lines[1]["text"] == "Backup completed"

    def test_add_external_job_output_not_registered(
        self, job_manager: JobManager
    ) -> None:
        """Test adding output to non-registered job"""
        job_manager.add_external_job_output("nonexistent", "some output")
        assert "nonexistent" not in job_manager.jobs

    def test_unregister_external_job(self, job_manager: JobManager) -> None:
        """Test unregistering external job"""
        job_id = "external-job-cleanup"
        job_manager.register_external_job(job_id, job_type="backup")

        assert job_id in job_manager.jobs

        job_manager.unregister_external_job(job_id)

        assert job_id not in job_manager.jobs

    def test_unregister_external_job_not_found(self, job_manager: JobManager) -> None:
        """Test unregistering non-existent job"""
        job_manager.unregister_external_job("nonexistent")  # Should not raise error


class TestJobManagerDatabaseIntegration:
    """Test database integration methods"""

    @pytest.fixture
    def job_manager_with_db(self, test_db: Session) -> JobManager:
        """Create job manager with real database session"""

        @contextmanager
        def db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        deps = JobManagerDependencies(db_session_factory=db_session_factory)
        full_deps = JobManagerFactory.create_dependencies(custom_dependencies=deps)
        manager = JobManager(dependencies=full_deps)
        return manager

    @pytest.mark.asyncio
    async def test_get_repository_data_success(
        self, job_manager_with_db: JobManager, sample_repository: Repository
    ) -> None:
        """Test getting repository data successfully"""
        # Mock the get_passphrase method to avoid encryption issues
        with patch.object(
            sample_repository, "get_passphrase", return_value="test-passphrase"
        ):
            result = await job_manager_with_db._get_repository_data(
                sample_repository.id
            )

        assert result is not None
        assert result["id"] == sample_repository.id
        assert result["name"] == "test-repo"
        assert result["path"] == "/tmp/test-repo"
        assert result["passphrase"] == "test-passphrase"

    @pytest.mark.asyncio
    async def test_get_repository_data_not_found(
        self, job_manager_with_db: JobManager
    ) -> None:
        """Test getting repository data for non-existent repository"""
        result = await job_manager_with_db._get_repository_data(99999)
        assert result is None


class TestJobManagerStreamingAndUtility:
    """Test streaming and utility methods"""

    @pytest.fixture
    def job_manager(self) -> JobManager:
        return JobManager()

    @pytest.mark.asyncio
    async def test_stream_job_output(self, job_manager: JobManager) -> None:
        """Test streaming job output"""
        job_id = "test-job"

        async def mock_stream() -> AsyncGenerator[Dict[str, Any], None]:
            yield {"line": "output line 1", "progress": {}}
            yield {"line": "output line 2", "progress": {"percent": 50}}

        job_manager.output_manager.stream_job_output = Mock(return_value=mock_stream())

        output_list = []
        async for output in job_manager.stream_job_output(job_id):
            output_list.append(output)

        assert len(output_list) == 2
        assert output_list[0]["line"] == "output line 1"
        assert output_list[1]["progress"]["percent"] == 50

    @pytest.mark.asyncio
    async def test_stream_job_output_no_manager(self) -> None:
        """Test streaming output when no output manager"""
        manager = JobManager()
        manager.output_manager = None

        output_list = []
        async for output in manager.stream_job_output("test"):
            output_list.append(output)

        assert len(output_list) == 0

    def test_get_job(self, job_manager: JobManager) -> None:
        """Test getting job by ID"""
        job = BorgJob(id="test", status="running", started_at=now_utc())
        job_manager.jobs["test"] = job

        retrieved = job_manager.get_job("test")
        assert retrieved is job

        assert job_manager.get_job("nonexistent") is None

    def test_list_jobs(self, job_manager: JobManager) -> None:
        """Test listing all jobs"""
        job1 = BorgJob(id="job1", status="running", started_at=now_utc())
        job2 = BorgJob(id="job2", status="completed", started_at=now_utc())

        job_manager.jobs["job1"] = job1
        job_manager.jobs["job2"] = job2

        jobs = job_manager.list_jobs()

        assert len(jobs) == 2
        assert jobs["job1"] is job1
        assert jobs["job2"] is job2
        assert jobs is not job_manager.jobs  # Should return copy

    @pytest.mark.asyncio
    async def test_get_job_output_stream(self, job_manager: JobManager) -> None:
        """Test getting job output stream data"""
        job_id = "test-job"

        # Mock output manager with job output data
        mock_output = Mock()
        mock_output.lines = [
            {"text": "line 1", "timestamp": "2024-01-01T12:00:00"},
            {"text": "line 2", "timestamp": "2024-01-01T12:00:01"},
        ]
        mock_output.current_progress = {"percent": 75}

        job_manager.output_manager.get_job_output = Mock(return_value=mock_output)

        result = await job_manager.get_job_output_stream(job_id)

        assert "lines" in result
        assert "progress" in result
        assert len(result["lines"]) == 2
        assert result["progress"]["percent"] == 75

    @pytest.mark.asyncio
    async def test_get_job_output_stream_no_output(
        self, job_manager: JobManager
    ) -> None:
        """Test getting output stream when no output exists"""
        job_manager.output_manager.get_job_output = Mock(return_value=None)

        result = await job_manager.get_job_output_stream("nonexistent")

        assert result["lines"] == []
        assert result["progress"] == {}

    def test_get_active_jobs_count(self, job_manager: JobManager) -> None:
        """Test getting count of active jobs"""
        job_manager.jobs = {
            "job1": Mock(status="running"),
            "job2": Mock(status="queued"),
            "job3": Mock(status="completed"),
            "job4": Mock(status="failed"),
            "job5": Mock(status="running"),
        }

        count = job_manager.get_active_jobs_count()
        assert count == 3  # 2 running + 1 queued

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, job_manager: JobManager) -> None:
        """Test cancelling a job successfully"""
        job = Mock(status="running")
        job_manager.jobs["test"] = job

        mock_process = AsyncMock()
        job_manager._processes["test"] = mock_process
        job_manager.executor.terminate_process = AsyncMock(return_value=True)

        result = await job_manager.cancel_job("test")

        assert result is True
        assert job.status == "cancelled"
        assert job.completed_at is not None
        assert "test" not in job_manager._processes

    @pytest.mark.asyncio
    async def test_cancel_job_not_cancellable(self, job_manager: JobManager) -> None:
        """Test cancelling job in non-cancellable state"""
        job = Mock(status="completed")
        job_manager.jobs["test"] = job

        result = await job_manager.cancel_job("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_manager: JobManager) -> None:
        """Test cancelling non-existent job"""
        result = await job_manager.cancel_job("nonexistent")
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

        deps = get_test_job_manager_dependencies(
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db_session,
            mock_rclone_service=mock_rclone,
        )

        assert deps.subprocess_executor is mock_subprocess
        assert deps.db_session_factory is mock_db_session
        assert deps.rclone_service is mock_rclone
