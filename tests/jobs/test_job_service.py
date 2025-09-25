"""
Tests for JobService business logic - Database operations and service methods
"""

import pytest
from unittest.mock import Mock, AsyncMock
from borgitory.utils.datetime_utils import now_utc

from sqlalchemy.orm import Session

from borgitory.services.jobs.job_service import JobService
from borgitory.models.database import (
    Repository,
    Job,
    PruneConfig,
    RepositoryCheckConfig,
)
from borgitory.models.schemas import (
    BackupRequest,
    PruneRequest,
    CheckRequest,
    CompressionType,
    PruneStrategy,
    CheckType,
)
from borgitory.models.enums import JobType


class TestJobService:
    """Test class for JobService."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create properly configured mocks with async methods
        self.mock_job_manager = Mock()
        self.mock_job_manager.create_composite_job = AsyncMock()
        self.mock_db = Mock()
        self.job_service = JobService(
            db=self.mock_db, job_manager=self.mock_job_manager
        )

    @pytest.mark.asyncio
    async def test_create_backup_job_simple(self, test_db: Session) -> None:
        """Test creating a simple backup job without additional tasks."""
        # Create test repository
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        # Configure mock return value
        self.mock_job_manager.create_composite_job.return_value = "job-123"

        backup_request = BackupRequest(
            repository_id=repository.id,
            source_path="/data",
            compression=CompressionType.LZ4,
            dry_run=False,
            cloud_sync_config_id=None,
            prune_config_id=None,
            check_config_id=None,
            notification_config_id=None,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_backup_job(
            backup_request, JobType.MANUAL_BACKUP
        )

        assert result["job_id"] == "job-123"
        assert result["status"] == "started"

        # Verify job manager was called with correct parameters
        self.mock_job_manager.create_composite_job.assert_called_once()
        call_args = self.mock_job_manager.create_composite_job.call_args
        assert call_args.kwargs["job_type"] == JobType.MANUAL_BACKUP
        assert len(call_args.kwargs["task_definitions"]) == 1
        assert call_args.kwargs["task_definitions"][0].type == "backup"

    @pytest.mark.asyncio
    async def test_create_backup_job_with_prune(self, test_db: Session) -> None:
        """Test creating a backup job with prune task."""
        # Create test data
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        prune_config = PruneConfig()
        prune_config.name = "test-prune"
        prune_config.strategy = "simple"
        prune_config.keep_within_days = 30
        prune_config.enabled = True
        prune_config.show_list = True
        prune_config.show_stats = True
        prune_config.save_space = False
        test_db.add_all([repository, prune_config])
        test_db.commit()

        self.mock_job_manager.create_composite_job = AsyncMock(return_value="job-123")

        backup_request = BackupRequest(
            repository_id=repository.id,
            source_path="/data",
            compression=CompressionType.LZ4,
            dry_run=False,
            prune_config_id=prune_config.id,
            cloud_sync_config_id=None,
            check_config_id=None,
            notification_config_id=None,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_backup_job(
            backup_request, JobType.MANUAL_BACKUP
        )

        assert result["job_id"] == "job-123"

        # Verify task definitions include prune task
        call_args = self.mock_job_manager.create_composite_job.call_args
        task_definitions = call_args.kwargs["task_definitions"]
        assert len(task_definitions) == 2
        assert task_definitions[0].type == "backup"
        assert task_definitions[1].type == "prune"
        assert task_definitions[1].parameters["keep_within"] == "30d"

    @pytest.mark.asyncio
    async def test_create_backup_job_repository_not_found(
        self, test_db: Session
    ) -> None:
        """Test backup job creation with non-existent repository."""
        backup_request = BackupRequest(
            repository_id=999,
            source_path="/data",
            compression=CompressionType.LZ4,
            dry_run=False,
            cloud_sync_config_id=None,
            prune_config_id=None,
            check_config_id=None,
            notification_config_id=None,
        )

        with pytest.raises(ValueError, match="Repository not found"):
            # Override mock db with real test_db for this test
            self.job_service.db = test_db
            await self.job_service.create_backup_job(
                backup_request, JobType.MANUAL_BACKUP
            )

    @pytest.mark.asyncio
    async def test_create_prune_job_simple_strategy(self, test_db: Session) -> None:
        """Test creating a prune job with simple retention strategy."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        # Configure mock return value
        self.mock_job_manager.create_composite_job.return_value = "prune-job-123"

        prune_request = PruneRequest(
            repository_id=repository.id,
            strategy=PruneStrategy.SIMPLE,
            keep_within_days=7,
            keep_daily=None,
            keep_weekly=None,
            keep_monthly=None,
            keep_yearly=None,
            keep_secondly=None,
            keep_minutely=None,
            keep_hourly=None,
            dry_run=False,
            show_list=True,
            show_stats=True,
            save_space=False,
            force_prune=False,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_prune_job(prune_request)

        assert result["job_id"] == "prune-job-123"
        assert result["status"] == "started"

        # Verify task definition
        call_args = self.mock_job_manager.create_composite_job.call_args
        task_def = call_args.kwargs["task_definitions"][0]
        assert task_def.type == "prune"
        assert task_def.parameters["keep_within"] == "7d"

    @pytest.mark.asyncio
    async def test_create_prune_job_advanced_strategy(self, test_db: Session) -> None:
        """Test creating a prune job with advanced retention strategy."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        # Configure mock return value
        self.mock_job_manager.create_composite_job.return_value = "prune-job-123"

        prune_request = PruneRequest(
            repository_id=repository.id,
            strategy=PruneStrategy.ADVANCED,
            keep_within_days=None,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
            keep_secondly=None,
            keep_minutely=None,
            keep_hourly=None,
            dry_run=False,
            show_list=True,
            show_stats=True,
            save_space=False,
            force_prune=False,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_prune_job(prune_request)

        assert result["job_id"] == "prune-job-123"

        # Verify task definition includes all retention parameters
        call_args = self.mock_job_manager.create_composite_job.call_args
        task_def = call_args.kwargs["task_definitions"][0]
        assert task_def.parameters["keep_daily"] == 7
        assert task_def.parameters["keep_weekly"] == 4
        assert task_def.parameters["keep_monthly"] == 6
        assert task_def.parameters["keep_yearly"] == 1

    @pytest.mark.asyncio
    async def test_create_check_job_with_config(self, test_db: Session) -> None:
        """Test creating a check job with existing check policy."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        check_config = RepositoryCheckConfig()
        check_config.name = "daily-check"
        check_config.check_type = "repository"
        check_config.verify_data = True
        check_config.repair_mode = False
        check_config.save_space = True
        check_config.max_duration = 3600
        check_config.enabled = True
        test_db.add_all([repository, check_config])
        test_db.commit()

        # Configure mock return value
        self.mock_job_manager.create_composite_job.return_value = "check-job-123"

        check_request = CheckRequest(
            repository_id=repository.id,
            check_config_id=check_config.id,
            max_duration=None,
            archive_prefix=None,
            archive_glob=None,
            first_n_archives=None,
            last_n_archives=None,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_check_job(check_request)

        assert result["job_id"] == "check-job-123"
        assert result["status"] == "started"

        # Verify task definition uses config parameters
        call_args = self.mock_job_manager.create_composite_job.call_args
        task_def = call_args.kwargs["task_definitions"][0]
        assert task_def.type == "check"
        assert task_def.parameters["check_type"] == "repository"
        assert task_def.parameters["verify_data"] is True
        assert task_def.parameters["save_space"] is True

    @pytest.mark.asyncio
    async def test_create_check_job_custom_parameters(self, test_db: Session) -> None:
        """Test creating a check job with custom parameters."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        # Configure mock return value
        self.mock_job_manager.create_composite_job.return_value = "check-job-123"

        check_request = CheckRequest(
            repository_id=repository.id,
            check_config_id=None,
            check_type=CheckType.ARCHIVES_ONLY,
            verify_data=False,
            repair_mode=False,
            save_space=False,
            max_duration=None,
            archive_prefix=None,
            archive_glob=None,
            first_n_archives=10,
            last_n_archives=None,
        )

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.create_check_job(check_request)

        assert result["job_id"] == "check-job-123"

        # Verify task definition uses custom parameters
        call_args = self.mock_job_manager.create_composite_job.call_args
        task_def = call_args.kwargs["task_definitions"][0]
        assert task_def.parameters["check_type"] == "archives_only"
        assert task_def.parameters["verify_data"] is False
        assert task_def.parameters["repair_mode"] is False
        assert task_def.parameters["first_n_archives"] == 10

    def test_list_jobs_database_only(self, test_db: Session) -> None:
        """Test listing jobs from database only."""
        # Create test jobs
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()  # Commit repository first to get ID

        job1 = Job()
        job1.repository_id = repository.id
        job1.type = "backup"
        job1.status = "completed"
        job2 = Job()
        job2.repository_id = repository.id
        job2.type = "prune"
        job2.status = "failed"
        test_db.add_all([job1, job2])
        test_db.commit()

        # Mock empty job manager
        self.mock_job_manager.jobs = {}

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        jobs = self.job_service.list_jobs(skip=0, limit=100)

        assert len(jobs) == 2
        # Jobs should be ordered by ID desc, but let's check what we actually get
        job_types = [job["type"] for job in jobs]
        assert "backup" in job_types
        assert "prune" in job_types
        assert all(job["source"] == "database" for job in jobs)

    def test_list_jobs_with_jobmanager(self, test_db: Session) -> None:
        """Test listing jobs including JobManager jobs."""
        # Create mock JobManager job
        mock_borg_job = Mock()
        mock_borg_job.status = "running"
        mock_borg_job.started_at = now_utc()
        mock_borg_job.completed_at = None
        mock_borg_job.error = None
        mock_borg_job.command = ["borg", "create", "repo::archive"]

        self.mock_job_manager.jobs = {"job-uuid": mock_borg_job}

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        jobs = self.job_service.list_jobs(skip=0, limit=100)

        # Should include the JobManager job
        jm_job = next((j for j in jobs if j["source"] == "jobmanager"), None)
        assert jm_job is not None
        assert jm_job["type"] == JobType.BACKUP  # Inferred from "create" command
        assert jm_job["status"] == "running"

    def test_get_job_from_database(self, test_db: Session) -> None:
        """Test getting a job from database by ID."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()  # Commit repository first to get ID

        job = Job()
        job.repository_id = repository.id
        job.type = "backup"
        job.status = "completed"
        test_db.add(job)
        test_db.commit()

        self.mock_job_manager.get_job_status.return_value = None

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = self.job_service.get_job(str(job.id))

        assert result is not None
        assert result["type"] == "backup"
        assert result["source"] == "database"
        assert result["repository_name"] == "test-repo"

    def test_get_job_from_jobmanager(self, test_db: Session) -> None:
        """Test getting a job from JobManager by UUID."""
        self.mock_job_manager.get_job_status.return_value = {
            "status": "running",
            "started_at": "2023-01-01T00:00:00",
            "completed_at": None,
            "error": None,
        }

        result = self.job_service.get_job("uuid-long-string")

        assert result is not None
        assert result["status"] == "running"
        assert result["source"] == "jobmanager"

    def test_get_job_not_found(self, test_db: Session) -> None:
        """Test getting a non-existent job."""
        self.mock_job_manager.get_job_status.return_value = None
        # Override mock db with real test_db for this test
        self.job_service.db = test_db

        result = self.job_service.get_job("999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_job_status(self) -> None:
        """Test getting job status."""
        expected_output = {"status": "running", "progress": 50}
        self.mock_job_manager.get_job_status.return_value = expected_output

        result = await self.job_service.get_job_status("job-123")

        assert result == expected_output
        self.mock_job_manager.get_job_status.assert_called_once_with("job-123")

    @pytest.mark.asyncio
    async def test_cancel_job_jobmanager(self, test_db: Session) -> None:
        """Test cancelling a JobManager job."""
        self.mock_job_manager.cancel_job = AsyncMock(return_value=True)

        result = await self.job_service.cancel_job("uuid-long-string")

        assert result is True
        self.mock_job_manager.cancel_job.assert_called_once_with("uuid-long-string")

    @pytest.mark.asyncio
    async def test_cancel_job_database(self, test_db: Session) -> None:
        """Test cancelling a database job."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()  # Commit repository first to get ID

        job = Job()
        job.repository_id = repository.id
        job.type = "backup"
        job.status = "running"
        test_db.add(job)
        test_db.commit()

        self.mock_job_manager.cancel_job = AsyncMock(return_value=False)

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.cancel_job(str(job.id))

        assert result is True

        # Verify job was marked as cancelled in database
        updated_job = test_db.query(Job).filter(Job.id == job.id).first()
        assert updated_job is not None
        assert updated_job.status == "cancelled"
        assert updated_job.finished_at is not None

    def test_get_manager_stats(self) -> None:
        """Test getting JobManager statistics."""
        # Mock job manager with different job statuses
        mock_running_job = Mock()
        mock_running_job.status = "running"
        mock_completed_job = Mock()
        mock_completed_job.status = "completed"
        mock_failed_job = Mock()
        mock_failed_job.status = "failed"

        self.mock_job_manager.jobs = {
            "job1": mock_running_job,
            "job2": mock_completed_job,
            "job3": mock_failed_job,
        }
        self.mock_job_manager._processes = ["proc1", "proc2"]

        stats = self.job_service.get_manager_stats()

        assert stats["total_jobs"] == 3
        assert stats["running_jobs"] == 1
        assert stats["completed_jobs"] == 1
        assert stats["failed_jobs"] == 1
        assert stats["active_processes"] == 2

    def test_cleanup_completed_jobs(self) -> None:
        """Test cleaning up completed jobs."""
        # Mock jobs with different statuses
        mock_running_job = Mock()
        mock_running_job.status = "running"
        mock_completed_job = Mock()
        mock_completed_job.status = "completed"
        mock_failed_job = Mock()
        mock_failed_job.status = "failed"

        self.mock_job_manager.jobs = {
            "job1": mock_running_job,
            "job2": mock_completed_job,
            "job3": mock_failed_job,
        }

        cleaned = self.job_service.cleanup_completed_jobs()

        assert cleaned == 2  # Should clean up completed and failed jobs
        assert self.mock_job_manager.cleanup_job.call_count == 2

    def test_get_queue_stats(self) -> None:
        """Test getting queue statistics."""
        expected_stats = {"queued": 3, "processing": 1}
        self.mock_job_manager.get_queue_stats.return_value = expected_stats

        stats = self.job_service.get_queue_stats()

        assert stats == expected_stats
