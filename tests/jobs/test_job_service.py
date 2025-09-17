"""
Tests for JobService business logic - Database operations and service methods
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from borgitory.services.jobs.job_service import JobService
from borgitory.models.database import (
    Repository,
    Job,
    CleanupConfig,
    RepositoryCheckConfig,
)
from borgitory.models.schemas import BackupRequest, PruneRequest, CheckRequest
from borgitory.models.enums import JobType


class TestJobService:
    """Test class for JobService."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_job_manager = Mock()
        self.mock_db = Mock()
        self.job_service = JobService(
            db=self.mock_db, job_manager=self.mock_job_manager
        )

    @pytest.mark.asyncio
    async def test_create_backup_job_simple(self, test_db: Session) -> None:
        """Test creating a simple backup job without additional tasks."""
        # Create test repository
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        # Mock the job manager
        self.mock_job_manager.create_composite_job = AsyncMock(return_value="job-123")

        backup_request = BackupRequest(
            repository_id=1, source_path="/data", compression="lz4", dry_run=False
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
        assert call_args.kwargs["task_definitions"][0]["type"] == "backup"

    @pytest.mark.asyncio
    async def test_create_backup_job_with_cleanup(self, test_db: Session) -> None:
        """Test creating a backup job with cleanup task."""
        # Create test data
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        cleanup_config = CleanupConfig(
            id=1,
            name="test-cleanup",
            strategy="simple",
            keep_within_days=30,
            enabled=True,
            show_list=True,
            show_stats=True,
            save_space=False,
        )
        test_db.add_all([repository, cleanup_config])
        test_db.commit()

        self.mock_job_manager.create_composite_job = AsyncMock(return_value="job-123")

        backup_request = BackupRequest(
            repository_id=1,
            source_path="/data",
            compression="lz4",
            dry_run=False,
            cleanup_config_id=1,
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
        assert task_definitions[0]["type"] == "backup"
        assert task_definitions[1]["type"] == "prune"
        assert task_definitions[1]["keep_within"] == "30d"

    @pytest.mark.asyncio
    async def test_create_backup_job_repository_not_found(self, test_db: Session) -> None:
        """Test backup job creation with non-existent repository."""
        backup_request = BackupRequest(
            repository_id=999, source_path="/data", compression="lz4", dry_run=False
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
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        with patch.object(
            self.job_service.job_manager, "create_composite_job", new_callable=AsyncMock
        ) as mock_create_job:
            mock_create_job.return_value = "prune-job-123"

            prune_request = PruneRequest(
                repository_id=1,
                strategy="simple",
                keep_within_days=7,
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
            call_args = mock_create_job.call_args
            task_def = call_args.kwargs["task_definitions"][0]
            assert task_def["type"] == "prune"
            assert task_def["keep_within"] == "7d"

    @pytest.mark.asyncio
    async def test_create_prune_job_advanced_strategy(self, test_db: Session) -> None:
        """Test creating a prune job with advanced retention strategy."""
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        with patch.object(
            self.job_service.job_manager, "create_composite_job", new_callable=AsyncMock
        ) as mock_create_job:
            mock_create_job.return_value = "prune-job-123"

            prune_request = PruneRequest(
                repository_id=1,
                strategy="advanced",
                keep_daily=7,
                keep_weekly=4,
                keep_monthly=6,
                keep_yearly=1,
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
            call_args = mock_create_job.call_args
            task_def = call_args.kwargs["task_definitions"][0]
            assert task_def["keep_daily"] == 7
            assert task_def["keep_weekly"] == 4
            assert task_def["keep_monthly"] == 6
            assert task_def["keep_yearly"] == 1

    @pytest.mark.asyncio
    async def test_create_check_job_with_config(self, test_db: Session) -> None:
        """Test creating a check job with existing check policy."""
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        check_config = RepositoryCheckConfig(
            id=1,
            name="daily-check",
            check_type="repository",
            verify_data=True,
            repair_mode=False,
            save_space=True,
            max_duration=3600,
            enabled=True,
        )
        test_db.add_all([repository, check_config])
        test_db.commit()

        with patch.object(
            self.job_service.job_manager, "create_composite_job", new_callable=AsyncMock
        ) as mock_create_job:
            mock_create_job.return_value = "check-job-123"

            check_request = CheckRequest(repository_id=1, check_config_id=1)

            # Override mock db with real test_db for this test
            self.job_service.db = test_db
            result = await self.job_service.create_check_job(check_request)

            assert result["job_id"] == "check-job-123"
            assert result["status"] == "started"

            # Verify task definition uses config parameters
            call_args = mock_create_job.call_args
            task_def = call_args.kwargs["task_definitions"][0]
            assert task_def["type"] == "check"
            assert task_def["check_type"] == "repository"
            assert task_def["verify_data"] is True
            assert task_def["save_space"] is True

    @pytest.mark.asyncio
    async def test_create_check_job_custom_parameters(self, test_db: Session) -> None:
        """Test creating a check job with custom parameters."""
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        with patch.object(
            self.job_service.job_manager, "create_composite_job", new_callable=AsyncMock
        ) as mock_create_job:
            mock_create_job.return_value = "check-job-123"

            check_request = CheckRequest(
                repository_id=1,
                check_type="archives_only",
                verify_data=False,
                repair_mode=False,
                save_space=False,
                first_n_archives=10,
            )

            # Override mock db with real test_db for this test
            self.job_service.db = test_db
            result = await self.job_service.create_check_job(check_request)

            assert result["job_id"] == "check-job-123"

            # Verify task definition uses custom parameters
            call_args = mock_create_job.call_args
            task_def = call_args.kwargs["task_definitions"][0]
            assert task_def["check_type"] == "archives_only"
            assert task_def["verify_data"] is False
            assert task_def["repair_mode"] is False
            assert task_def["first_n_archives"] == 10

    def test_list_jobs_database_only(self, test_db: Session) -> None:
        """Test listing jobs from database only."""
        # Create test jobs
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        job1 = Job(id=1, repository_id=1, type="backup", status="completed")
        job2 = Job(id=2, repository_id=1, type="prune", status="failed")
        test_db.add_all([repository, job1, job2])
        test_db.commit()

        # Mock empty job manager
        self.mock_job_manager.jobs = {}

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        jobs = self.job_service.list_jobs(skip=0, limit=100)

        assert len(jobs) == 2
        assert jobs[0]["type"] == "prune"  # Ordered by ID desc
        assert jobs[0]["source"] == "database"
        assert jobs[1]["type"] == "backup"
        assert jobs[1]["source"] == "database"

    def test_list_jobs_with_jobmanager(self, test_db: Session) -> None:
        """Test listing jobs including JobManager jobs."""
        # Create mock JobManager job
        mock_borg_job = Mock()
        mock_borg_job.status = "running"
        mock_borg_job.started_at = datetime.now(UTC)
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
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        job = Job(id=1, repository_id=1, type="backup", status="completed")
        test_db.add_all([repository, job])
        test_db.commit()

        self.mock_job_manager.get_job_status.return_value = None

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = self.job_service.get_job("1")

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
        self.mock_job_manager.get_job_output_stream = AsyncMock(
            return_value=expected_output
        )

        result = await self.job_service.get_job_status("job-123")

        assert result == expected_output
        self.mock_job_manager.get_job_output_stream.assert_called_once_with(
            "job-123", last_n_lines=50
        )

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
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        job = Job(id=1, repository_id=1, type="backup", status="running")
        test_db.add_all([repository, job])
        test_db.commit()

        self.mock_job_manager.cancel_job = AsyncMock(return_value=False)

        # Override mock db with real test_db for this test
        self.job_service.db = test_db
        result = await self.job_service.cancel_job("1")

        assert result is True

        # Verify job was marked as cancelled in database
        updated_job = test_db.query(Job).filter(Job.id == 1).first()
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
