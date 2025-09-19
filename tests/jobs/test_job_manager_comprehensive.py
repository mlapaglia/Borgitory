"""
Comprehensive tests for JobManager - covering missing lines and functionality
"""

import pytest
import uuid
import asyncio
import os
from datetime import datetime, UTC
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
    create_job_manager,
    get_default_job_manager_dependencies,
    get_test_job_manager_dependencies,
)
from borgitory.services.jobs.job_executor import ProcessResult
from borgitory.models.database import NotificationConfig


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
        assert deps.pushover_service is not None

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
    def job_manager_with_db(self, test_db: Session):
        """Create job manager with real database session"""

        @contextmanager
        def db_session_factory():
            try:
                yield test_db
            finally:
                pass

        deps = JobManagerDependencies(db_session_factory=db_session_factory)
        full_deps = JobManagerFactory.create_dependencies(custom_dependencies=deps)
        manager = JobManager(dependencies=full_deps)
        return manager

    @pytest.mark.asyncio
    async def test_create_composite_job(
        self, job_manager_with_db, sample_repository
    ) -> None:
        """Test creating a composite job with multiple tasks"""
        task_definitions = [
            {
                "type": "backup",
                "name": "Backup data",
                "paths": ["/tmp"],
                "excludes": ["*.tmp"],
            },
            {
                "type": "prune",
                "name": "Prune old archives",
                "keep_daily": 7,
                "keep_weekly": 4,
            },
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
        self, job_manager_with_db, sample_repository
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
            started_at=datetime.now(UTC),
            tasks=[task1, task2],
            repository_id=sample_repository.id,
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock individual task execution to succeed
        async def mock_backup_task(job, task, task_index):
            task.status = "completed"
            task.return_code = 0
            task.completed_at = datetime.now(UTC)
            return True

        async def mock_prune_task(job, task, task_index):
            task.status = "completed"
            task.return_code = 0
            task.completed_at = datetime.now(UTC)
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
        self, job_manager_with_db, sample_repository
    ) -> None:
        """Test composite job with critical task failure"""
        job_id = str(uuid.uuid4())
        task1 = BorgJobTask(
            task_type="backup", task_name="Test Backup"
        )  # Critical task
        task2 = BorgJobTask(task_type="prune", task_name="Test Prune")

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="pending",
            started_at=datetime.now(UTC),
            tasks=[task1, task2],
            repository_id=sample_repository.id,
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock backup to fail (critical)
        async def mock_backup_fail(job, task, task_index):
            task.status = "failed"
            task.return_code = 1
            task.error = "Backup failed"
            task.completed_at = datetime.now(UTC)
            return False

        # Prune should not be called due to critical failure
        mock_prune = AsyncMock()

        with patch.object(
            job_manager_with_db, "_execute_backup_task", side_effect=mock_backup_fail
        ), patch.object(job_manager_with_db, "_execute_prune_task", mock_prune):
            await job_manager_with_db._execute_composite_job(job)

        # Verify job failed due to critical task failure
        assert job.status == "failed"
        assert task1.status == "failed"

        # Prune should not have been called
        mock_prune.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_backup_task_success(
        self, job_manager_with_db, sample_repository
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
            started_at=datetime.now(UTC),
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
        self, job_manager_with_db, sample_repository
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
            started_at=datetime.now(UTC),
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
        assert "Backup failed" in task.error

    @pytest.mark.asyncio
    async def test_execute_prune_task_success(self, job_manager_with_db) -> None:
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
            started_at=datetime.now(UTC),
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
        self, job_manager_with_db, sample_repository
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
            started_at=datetime.now(UTC),
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
    async def test_execute_cloud_sync_task_success(self, job_manager_with_db) -> None:
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
            started_at=datetime.now(UTC),
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
        self, job_manager_with_db, test_db
    ) -> None:
        """Test successful notification task execution"""
        # Create notification config in database
        notification_config = NotificationConfig(
            name="Test Pushover",
            provider="pushover",
            enabled=True,
            encrypted_user_key="encrypted_user_key",
            encrypted_app_token="encrypted_app_token",
        )
        test_db.add(notification_config)
        test_db.commit()

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
            started_at=datetime.now(UTC),
            tasks=[task],
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        # Mock successful notification with proper database access
        with patch.object(
            notification_config,
            "get_pushover_credentials",
            return_value=("user_key", "app_token"),
        ), patch("borgitory.services.jobs.job_manager.get_db_session") as mock_get_db:
            # Set up the database session context manager
            mock_get_db.return_value.__enter__.return_value = test_db

            job_manager_with_db.pushover_service.send_notification_with_response = (
                AsyncMock(return_value=(True, "Message sent"))
            )

            success = await job_manager_with_db._execute_notification_task(job, task)

        assert success is True
        assert task.status == "completed"
        assert task.return_code == 0
        assert len(task.output_lines) > 0

    @pytest.mark.asyncio
    async def test_execute_notification_task_no_config(
        self, job_manager_with_db
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
            started_at=datetime.now(UTC),
            tasks=[task],
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        success = await job_manager_with_db._execute_notification_task(job, task)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert "No notification configuration" in task.error

    @pytest.mark.asyncio
    async def test_execute_task_unknown_type(self, job_manager_with_db) -> None:
        """Test executing task with unknown type"""
        job_id = str(uuid.uuid4())
        task = BorgJobTask(task_type="unknown_task", task_name="Unknown Task")

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="running",
            started_at=datetime.now(UTC),
            tasks=[task],
        )
        job_manager_with_db.jobs[job_id] = job
        job_manager_with_db.output_manager.create_job_output(job_id)

        success = await job_manager_with_db._execute_task(job, task)

        assert success is False
        assert task.status == "failed"
        assert task.return_code == 1
        assert "Unknown task type: unknown_task" in task.error


class TestJobManagerExternalIntegration:
    """Test external job registration and management"""

    @pytest.fixture
    def job_manager(self):
        """Create job manager for testing"""
        return JobManager()

    def test_register_external_job(self, job_manager) -> None:
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

    def test_update_external_job_status(self, job_manager) -> None:
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

    def test_update_external_job_status_with_error(self, job_manager) -> None:
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

    def test_update_external_job_status_not_registered(self, job_manager) -> None:
        """Test updating status for non-registered job"""
        # Should not raise error
        job_manager.update_external_job_status("nonexistent", "completed")
        assert "nonexistent" not in job_manager.jobs

    @pytest.mark.asyncio
    async def test_add_external_job_output(self, job_manager) -> None:
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

    def test_add_external_job_output_not_registered(self, job_manager) -> None:
        """Test adding output to non-registered job"""
        job_manager.add_external_job_output("nonexistent", "some output")
        assert "nonexistent" not in job_manager.jobs

    def test_unregister_external_job(self, job_manager) -> None:
        """Test unregistering external job"""
        job_id = "external-job-cleanup"
        job_manager.register_external_job(job_id, job_type="backup")

        assert job_id in job_manager.jobs

        job_manager.unregister_external_job(job_id)

        assert job_id not in job_manager.jobs

    def test_unregister_external_job_not_found(self, job_manager) -> None:
        """Test unregistering non-existent job"""
        job_manager.unregister_external_job("nonexistent")  # Should not raise error


class TestJobManagerDatabaseIntegration:
    """Test database integration methods"""

    @pytest.fixture
    def job_manager_with_db(self, test_db: Session):
        """Create job manager with real database session"""

        @contextmanager
        def db_session_factory():
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
        self, job_manager_with_db, sample_repository
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
    async def test_get_repository_data_not_found(self, job_manager_with_db) -> None:
        """Test getting repository data for non-existent repository"""
        result = await job_manager_with_db._get_repository_data(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_repository_data_fallback_mechanisms(
        self, job_manager_with_db, sample_repository
    ) -> None:
        """Test repository data fallback when database manager fails"""
        # Mock database manager to fail and fix passphrase
        job_manager_with_db.database_manager.get_repository_data = AsyncMock(
            side_effect=Exception("DB error")
        )

        with patch.object(
            sample_repository, "get_passphrase", return_value="test-passphrase"
        ):
            result = await job_manager_with_db._get_repository_data(
                sample_repository.id
            )

        # Should fall back to direct database access
        assert result is not None
        assert result["id"] == sample_repository.id


class TestJobManagerStreamingAndUtility:
    """Test streaming and utility methods"""

    @pytest.fixture
    def job_manager(self):
        return JobManager()

    @pytest.mark.asyncio
    async def test_stream_job_output(self, job_manager) -> None:
        """Test streaming job output"""
        job_id = "test-job"

        async def mock_stream():
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

    def test_get_job(self, job_manager) -> None:
        """Test getting job by ID"""
        job = BorgJob(id="test", status="running", started_at=datetime.now(UTC))
        job_manager.jobs["test"] = job

        retrieved = job_manager.get_job("test")
        assert retrieved is job

        assert job_manager.get_job("nonexistent") is None

    def test_list_jobs(self, job_manager) -> None:
        """Test listing all jobs"""
        job1 = BorgJob(id="job1", status="running", started_at=datetime.now(UTC))
        job2 = BorgJob(id="job2", status="completed", started_at=datetime.now(UTC))

        job_manager.jobs["job1"] = job1
        job_manager.jobs["job2"] = job2

        jobs = job_manager.list_jobs()

        assert len(jobs) == 2
        assert jobs["job1"] is job1
        assert jobs["job2"] is job2
        assert jobs is not job_manager.jobs  # Should return copy

    @pytest.mark.asyncio
    async def test_get_job_output_stream(self, job_manager) -> None:
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
    async def test_get_job_output_stream_no_output(self, job_manager) -> None:
        """Test getting output stream when no output exists"""
        job_manager.output_manager.get_job_output = Mock(return_value=None)

        result = await job_manager.get_job_output_stream("nonexistent")

        assert result["lines"] == []
        assert result["progress"] == {}

    def test_get_active_jobs_count(self, job_manager) -> None:
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
    async def test_cancel_job_success(self, job_manager) -> None:
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
    async def test_cancel_job_not_cancellable(self, job_manager) -> None:
        """Test cancelling job in non-cancellable state"""
        job = Mock(status="completed")
        job_manager.jobs["test"] = job

        result = await job_manager.cancel_job("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_manager) -> None:
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

    def test_create_job_manager_with_environment_config(self) -> None:
        """Test creating job manager with environment variables"""
        with patch.dict(
            os.environ,
            {
                "BORG_MAX_CONCURRENT_BACKUPS": "8",
                "BORG_MAX_OUTPUT_LINES": "1500",
            },
        ):
            manager = create_job_manager()

            assert manager.config.max_concurrent_backups == 8
            assert manager.config.max_output_lines_per_job == 1500
