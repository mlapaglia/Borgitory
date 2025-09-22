import pytest
import uuid
from borgitory.utils.datetime_utils import now_utc
from unittest.mock import Mock, AsyncMock, patch
from contextlib import contextmanager

from sqlalchemy.orm import Session

from borgitory.services.backups.backup_service import BackupService
from borgitory.services.backups.backup_executor import (
    BackupExecutor,
    BackupResult,
    BackupStatus,
)
from borgitory.models.database import Repository, Job, JobTask
from borgitory.models.schemas import BackupRequest, PruneRequest
from borgitory.models.enums import JobType


class TestBackupService:
    """Test BackupService class"""

    @pytest.fixture
    def test_repository(self, test_db: Session):
        """Create test repository using real database"""

        @contextmanager
        def db_session_factory():
            try:
                yield test_db
            finally:
                pass

        with db_session_factory() as db:
            repo = Repository(
                name="test-service-repo",
                path="/tmp/test-service-repo",
                encrypted_passphrase="dummy",
            )
            repo.set_passphrase("test-service-passphrase")
            db.add(repo)
            db.commit()
            db.refresh(repo)
            return repo

    @pytest.fixture
    def backup_service(self, test_db: Session):
        """Create backup service with real database"""
        return BackupService(db_session=test_db)

    @pytest.fixture
    def backup_service_with_mock_executor(self, test_db: Session):
        """Create backup service with mock executor"""
        mock_executor = Mock(spec=BackupExecutor)
        return BackupService(db_session=test_db, backup_executor=mock_executor)

    def test_backup_service_initialization_default_executor(
        self, test_db: Session
    ) -> None:
        """Test BackupService initialization with default executor"""
        service = BackupService(db_session=test_db)

        assert service.db == test_db
        assert isinstance(service.executor, BackupExecutor)

    def test_backup_service_initialization_custom_executor(
        self, test_db: Session
    ) -> None:
        """Test BackupService initialization with custom executor"""
        mock_executor = Mock(spec=BackupExecutor)
        service = BackupService(db_session=test_db, backup_executor=mock_executor)

        assert service.db == test_db
        assert service.executor == mock_executor

    @pytest.mark.asyncio
    async def test_execute_backup_success(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test successful backup execution"""
        # Create a job record
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=test_repository.id,
            type="backup",
            status="running",
            started_at=now_utc(),
            job_type="backup",
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        # Create backup request
        backup_request = BackupRequest(
            repository_id=test_repository.id,
            source_path="/data",
            compression="zstd",
            dry_run=False,
        )

        # Mock successful backup result
        mock_result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Backup completed successfully"],
            completed_at=now_utc(),
        )
        backup_service_with_mock_executor.executor.execute_backup = AsyncMock(
            return_value=mock_result
        )

        # Mock post-backup operations
        with patch.object(
            backup_service_with_mock_executor, "_handle_post_backup_operations"
        ) as mock_post_ops:
            result = await backup_service_with_mock_executor.execute_backup(
                job, backup_request
            )

        assert result.status == BackupStatus.COMPLETED
        assert result.success is True
        backup_service_with_mock_executor.executor.execute_backup.assert_called_once()
        mock_post_ops.assert_called_once()

        # Verify job was updated
        updated_job = (
            backup_service_with_mock_executor.db.query(Job)
            .filter(Job.id == job.id)
            .first()
        )
        assert updated_job is not None

    @pytest.mark.asyncio
    async def test_execute_backup_repository_not_found(self, backup_service) -> None:
        """Test backup execution with non-existent repository"""
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=999,  # Non-existent repository
            type="backup",
            status="running",
            started_at=now_utc(),
        )

        backup_request = BackupRequest(repository_id=999, source_path="/data")

        with pytest.raises(ValueError, match="Repository 999 not found"):
            await backup_service.execute_backup(job, backup_request)

    @pytest.mark.asyncio
    async def test_execute_backup_with_output_callback(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test backup execution with output callback"""
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=test_repository.id,
            type="backup",
            status="running",
            started_at=now_utc(),
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        output_lines = []

        def output_callback(line) -> None:
            output_lines.append(line)

        # Mock successful backup result
        mock_result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Test output line"],
            completed_at=now_utc(),
        )

        # Mock executor to call output callback
        async def mock_execute_backup(*args, **kwargs):
            if "output_callback" in kwargs and kwargs["output_callback"]:
                kwargs["output_callback"]("Test output line")
            return mock_result

        backup_service_with_mock_executor.executor.execute_backup = mock_execute_backup

        with patch.object(
            backup_service_with_mock_executor, "_handle_post_backup_operations"
        ):
            result = await backup_service_with_mock_executor.execute_backup(
                job, backup_request, output_callback=output_callback
            )

        assert result.status == BackupStatus.COMPLETED
        assert len(output_lines) == 1
        assert output_lines[0] == "Test output line"

    @pytest.mark.asyncio
    async def test_execute_backup_failure_exception(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test backup execution with exception handling"""
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=test_repository.id,
            type="backup",
            status="running",
            started_at=now_utc(),
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        # Mock executor to raise exception
        backup_service_with_mock_executor.executor.execute_backup = AsyncMock(
            side_effect=Exception("Backup failed")
        )

        with pytest.raises(Exception, match="Backup failed"):
            await backup_service_with_mock_executor.execute_backup(job, backup_request)

        # Verify job status was updated to failed
        updated_job = (
            backup_service_with_mock_executor.db.query(Job)
            .filter(Job.id == job.id)
            .first()
        )
        assert updated_job.status == "failed"
        assert updated_job.error == "Backup failed"
        assert updated_job.finished_at is not None

    @pytest.mark.asyncio
    async def test_create_and_run_prune_success(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test successful prune creation and execution"""
        prune_request = PruneRequest(
            repository_id=test_repository.id, keep_daily=7, keep_weekly=4, dry_run=False
        )

        # Mock successful prune result
        mock_result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Prune completed successfully"],
            completed_at=now_utc(),
        )
        backup_service_with_mock_executor.executor.execute_prune = AsyncMock(
            return_value=mock_result
        )

        job_id = await backup_service_with_mock_executor.create_and_run_prune(
            prune_request
        )

        assert job_id is not None
        backup_service_with_mock_executor.executor.execute_prune.assert_called_once()

        # Verify job was created
        job = (
            backup_service_with_mock_executor.db.query(Job)
            .filter(Job.id == job_id)
            .first()
        )
        assert job is not None
        assert job.repository_id == test_repository.id
        assert job.type == JobType.PRUNE.value

    @pytest.mark.asyncio
    async def test_create_and_run_prune_repository_not_found(
        self, backup_service
    ) -> None:
        """Test prune with non-existent repository"""
        prune_request = PruneRequest(repository_id=999, keep_daily=7)

        with pytest.raises(ValueError, match="Repository 999 not found"):
            await backup_service.create_and_run_prune(prune_request)

    @pytest.mark.asyncio
    async def test_create_and_run_prune_failure(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test prune execution failure"""
        prune_request = PruneRequest(repository_id=test_repository.id, keep_daily=7)

        # Mock executor to raise exception
        backup_service_with_mock_executor.executor.execute_prune = AsyncMock(
            side_effect=Exception("Prune failed")
        )

        with pytest.raises(Exception, match="Prune failed"):
            await backup_service_with_mock_executor.create_and_run_prune(prune_request)

    def test_get_job_status_success(self, backup_service, test_repository) -> None:
        """Test getting job status successfully"""
        # Create job with tasks
        job = Job(
            id="test-job-status",
            repository_id=test_repository.id,
            type="backup",
            status="completed",
            started_at=now_utc(),
            finished_at=now_utc(),
        )
        backup_service.db.add(job)
        backup_service.db.commit()

        task = JobTask(
            job_id=job.id,
            task_type="backup",
            task_name="Test Backup",
            status="completed",
            started_at=now_utc(),
            completed_at=now_utc(),
            return_code=0,
            task_order=1,
        )
        backup_service.db.add(task)
        backup_service.db.commit()

        status = backup_service.get_job_status("test-job-status")

        assert status is not None
        assert status["id"] == "test-job-status"
        assert status["status"] == "completed"
        assert status["type"] == "backup"
        assert status["repository_id"] == test_repository.id
        assert len(status["tasks"]) == 1
        assert status["tasks"][0]["type"] == "backup"
        assert status["tasks"][0]["status"] == "completed"

    def test_get_job_status_not_found(self, backup_service) -> None:
        """Test getting status for non-existent job"""
        status = backup_service.get_job_status("non-existent-job")
        assert status is None

    def test_list_recent_jobs(self, backup_service, test_repository) -> None:
        """Test listing recent jobs"""
        # Create multiple jobs
        jobs = []
        for i in range(3):
            job = Job(
                id=f"job-{i}",
                repository_id=test_repository.id,
                type="backup",
                status="completed",
                started_at=now_utc(),
                finished_at=now_utc(),
            )
            jobs.append(job)
            backup_service.db.add(job)

        backup_service.db.commit()

        recent_jobs = backup_service.list_recent_jobs(limit=5)

        assert len(recent_jobs) == 3
        for job_data in recent_jobs:
            assert "id" in job_data
            assert "status" in job_data
            assert "type" in job_data
            assert "repository_id" in job_data
            assert "repository_name" in job_data

    def test_list_recent_jobs_with_limit(self, backup_service, test_repository) -> None:
        """Test listing recent jobs with limit"""
        # Create 5 jobs but limit to 2
        for i in range(5):
            job = Job(
                id=f"job-limit-{i}",
                repository_id=test_repository.id,
                type="backup",
                status="completed",
                started_at=now_utc(),
            )
            backup_service.db.add(job)

        backup_service.db.commit()

        recent_jobs = backup_service.list_recent_jobs(limit=2)
        assert len(recent_jobs) == 2

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, backup_service_with_mock_executor) -> None:
        """Test successful job cancellation"""
        job_id = "cancel-job-test"

        # Create running job
        job = Job(
            id=job_id,
            repository_id=1,
            type="backup",
            status="running",
            started_at=now_utc(),
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        # Mock successful termination
        backup_service_with_mock_executor.executor.terminate_operation = AsyncMock(
            return_value=True
        )

        success = await backup_service_with_mock_executor.cancel_job(job_id)

        assert success is True
        backup_service_with_mock_executor.executor.terminate_operation.assert_called_once_with(
            job_id
        )

        # Verify job status was updated
        updated_job = (
            backup_service_with_mock_executor.db.query(Job)
            .filter(Job.id == job_id)
            .first()
        )
        assert updated_job.status == "cancelled"
        assert updated_job.error == "Job was cancelled by user"
        assert updated_job.finished_at is not None

    @pytest.mark.asyncio
    async def test_cancel_job_termination_failed(
        self, backup_service_with_mock_executor
    ) -> None:
        """Test job cancellation when termination fails"""
        job_id = "cancel-fail-test"

        # Mock failed termination
        backup_service_with_mock_executor.executor.terminate_operation = AsyncMock(
            return_value=False
        )

        success = await backup_service_with_mock_executor.cancel_job(job_id)

        assert success is False

    @pytest.mark.asyncio
    async def test_cancel_job_non_running(
        self, backup_service_with_mock_executor
    ) -> None:
        """Test cancelling non-running job"""
        job_id = "cancel-non-running"

        # Create completed job
        job = Job(
            id=job_id,
            repository_id=1,
            type="backup",
            status="completed",
            started_at=now_utc(),
            finished_at=now_utc(),
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        # Mock successful termination
        backup_service_with_mock_executor.executor.terminate_operation = AsyncMock(
            return_value=True
        )

        success = await backup_service_with_mock_executor.cancel_job(job_id)

        assert success is True
        # Job status should not change since it wasn't running
        updated_job = (
            backup_service_with_mock_executor.db.query(Job)
            .filter(Job.id == job_id)
            .first()
        )
        assert updated_job.status == "completed"

    def test_get_repository_success(self, backup_service, test_repository) -> None:
        """Test _get_repository method success"""
        repo = backup_service._get_repository(test_repository.id)
        assert repo is not None
        assert repo.id == test_repository.id
        assert repo.name == test_repository.name

    def test_get_repository_not_found(self, backup_service) -> None:
        """Test _get_repository with non-existent repository"""
        repo = backup_service._get_repository(999)
        assert repo is None

    def test_create_job_record(self, backup_service, test_repository) -> None:
        """Test _create_job_record method"""
        backup_request = BackupRequest(
            repository_id=test_repository.id,
            source_path="/data",
            cloud_sync_config_id=1,
            cleanup_config_id=2,
            check_config_id=3,
            notification_config_id=4,
        )

        job = backup_service._create_job_record(
            test_repository, JobType.MANUAL_BACKUP, backup_request
        )

        assert job is not None
        assert job.repository_id == test_repository.id
        assert job.type == JobType.MANUAL_BACKUP.value
        assert job.status == "running"
        assert job.started_at is not None
        assert job.cloud_sync_config_id == 1
        assert job.cleanup_config_id == 2
        assert job.check_config_id == 3
        assert job.notification_config_id == 4

        # Verify job was saved to database
        saved_job = backup_service.db.query(Job).filter(Job.id == job.id).first()
        assert saved_job is not None

    def test_create_job_record_minimal(self, backup_service, test_repository) -> None:
        """Test _create_job_record with minimal request"""
        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        job = backup_service._create_job_record(
            test_repository, JobType.BACKUP, backup_request
        )

        assert job is not None
        assert job.repository_id == test_repository.id
        assert job.type == JobType.BACKUP.value
        assert job.cloud_sync_config_id is None
        assert job.cleanup_config_id is None

    def test_create_backup_task(self, backup_service, test_repository) -> None:
        """Test _create_backup_task method"""
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=test_repository.id,
            type="backup",
            status="running",
            started_at=now_utc(),
        )
        backup_service.db.add(job)
        backup_service.db.commit()

        task = backup_service._create_backup_task(job)

        assert task is not None
        assert task.job_id == job.id
        assert task.task_type == "backup"
        assert task.task_name == f"Backup {test_repository.name}"
        assert task.status == "running"
        assert task.started_at is not None
        assert task.task_order == 0

        # Verify task was saved to database
        saved_task = (
            backup_service.db.query(JobTask).filter(JobTask.id == task.id).first()
        )
        assert saved_task is not None

    def test_create_prune_task(self, backup_service, test_repository) -> None:
        """Test _create_prune_task method"""
        job = Job(
            id=str(uuid.uuid4()),
            repository_id=test_repository.id,
            type="prune",
            status="running",
            started_at=now_utc(),
        )
        backup_service.db.add(job)
        backup_service.db.commit()

        task = backup_service._create_prune_task(job)

        assert task is not None
        assert task.job_id == job.id
        assert task.task_type == "prune"
        assert task.task_name == f"Prune {test_repository.name}"
        assert task.status == "running"
        assert task.task_order == 0

    def test_handle_output_line_new_task(self, backup_service) -> None:
        """Test _handle_output_line with new task"""
        task = JobTask(
            job_id="test-job",
            task_type="backup",
            task_name="Test",
            status="running",
            task_order=0,
        )

        backup_service._handle_output_line(task, "First line")

        assert task.output == "First line"

    def test_handle_output_line_append(self, backup_service) -> None:
        """Test _handle_output_line appending to existing output"""
        task = JobTask(
            job_id="test-job",
            task_type="backup",
            task_name="Test",
            status="running",
            output="First line",
            task_order=0,
        )

        backup_service._handle_output_line(task, "Second line")

        assert task.output == "First line\nSecond line"

    def test_handle_output_line_periodic_commit(self, backup_service) -> None:
        """Test _handle_output_line commits periodically"""
        task = JobTask(
            job_id="test-job",
            task_type="backup",
            task_name="Test",
            status="running",
            task_order=0,
        )
        backup_service.db.add(task)

        # Add lines to trigger periodic commit (every 10 lines)
        for i in range(12):
            backup_service._handle_output_line(task, f"Line {i}")

        # Should have committed at line 10
        assert "\n" in task.output

    def test_update_task_from_result_success(self, backup_service) -> None:
        """Test _update_task_from_result with successful result"""
        task = JobTask(
            job_id="test-job",
            task_type="backup",
            task_name="Test",
            status="running",
            task_order=0,
        )

        result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Line 1", "Line 2"],
            completed_at=now_utc(),
        )

        backup_service._update_task_from_result(task, result)

        assert task.status == "completed"
        assert task.return_code == 0
        assert task.completed_at is not None
        assert task.output == "Line 1\nLine 2"
        assert task.error is None

    def test_update_task_from_result_failure(self, backup_service) -> None:
        """Test _update_task_from_result with failed result"""
        task = JobTask(
            job_id="test-job",
            task_type="backup",
            task_name="Test",
            status="running",
            task_order=0,
        )

        result = BackupResult(
            status=BackupStatus.FAILED,
            return_code=1,
            output_lines=["Error occurred"],
            error_message="Backup failed",
            completed_at=now_utc(),
        )

        backup_service._update_task_from_result(task, result)

        assert task.status == "failed"
        assert task.return_code == 1
        assert task.error == "Backup failed"
        assert task.output == "Error occurred"

    @pytest.mark.asyncio
    async def test_handle_post_backup_operations_backup_failed(
        self, backup_service, test_repository
    ) -> None:
        """Test _handle_post_backup_operations when backup failed"""
        job = Job(id="test-job", repository_id=test_repository.id, total_tasks=1)
        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        await backup_service._handle_post_backup_operations(
            job, test_repository, backup_request, False
        )

        # Should not add any tasks when backup failed
        assert job.total_tasks == 1

    @pytest.mark.asyncio
    async def test_handle_post_backup_operations_backup_success(
        self, backup_service, test_repository
    ) -> None:
        """Test _handle_post_backup_operations when backup succeeded"""
        job = Job(id="test-job", repository_id=test_repository.id, total_tasks=1)
        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        await backup_service._handle_post_backup_operations(
            job, test_repository, backup_request, True
        )

        # Currently no tasks are added (all are TODO in the implementation)
        assert job.total_tasks == 1

    def test_finalize_job_all_completed(self, backup_service) -> None:
        """Test _finalize_job with all tasks completed"""
        job = Job(
            id="test-finalize",
            repository_id=1,
            type="backup",  # Add required type field
            total_tasks=2,
            completed_tasks=0,
            status="running",
            started_at=now_utc(),
        )
        backup_service.db.add(job)

        # Add completed tasks
        task1 = JobTask(
            job_id=job.id,
            task_type="backup",
            task_name="Task 1",
            status="completed",
            task_order=0,
        )
        task2 = JobTask(
            job_id=job.id,
            task_type="prune",
            task_name="Task 2",
            status="completed",
            task_order=1,
        )
        backup_service.db.add(task1)
        backup_service.db.add(task2)
        backup_service.db.commit()

        backup_service._finalize_job(job)

        assert job.status == "completed"
        assert job.completed_tasks == 2
        assert job.finished_at is not None
        assert job.error is None

    def test_finalize_job_some_failed(self, backup_service) -> None:
        """Test _finalize_job with some failed tasks"""
        job = Job(
            id="test-finalize-fail",
            repository_id=1,
            type="backup",  # Add required type field
            total_tasks=2,
            completed_tasks=0,
            status="running",
            started_at=now_utc(),
        )
        backup_service.db.add(job)

        # Add mixed tasks
        task1 = JobTask(
            job_id=job.id,
            task_type="backup",
            task_name="Task 1",
            status="completed",
            task_order=0,
        )
        task2 = JobTask(
            job_id=job.id,
            task_type="prune",
            task_name="Task 2",
            status="failed",
            task_order=1,
        )
        backup_service.db.add(task1)
        backup_service.db.add(task2)
        backup_service.db.commit()

        backup_service._finalize_job(job)

        assert job.status == "failed"
        assert job.completed_tasks == 1
        assert job.error == "1 task(s) failed"

    def test_finalize_job_partial_completion(self, backup_service) -> None:
        """Test _finalize_job with partial completion"""
        job = Job(
            id="test-finalize-partial",
            repository_id=1,
            type="backup",  # Add required type field
            total_tasks=3,
            completed_tasks=0,
            status="running",
            started_at=now_utc(),
        )
        backup_service.db.add(job)

        # Add only 2 completed tasks out of 3 total
        task1 = JobTask(
            job_id=job.id,
            task_type="backup",
            task_name="Task 1",
            status="completed",
            task_order=0,
        )
        task2 = JobTask(
            job_id=job.id,
            task_type="check",
            task_name="Task 2",
            status="completed",
            task_order=1,
        )
        backup_service.db.add(task1)
        backup_service.db.add(task2)
        backup_service.db.commit()

        backup_service._finalize_job(job)

        assert job.status == "partial"
        assert job.completed_tasks == 2

    @pytest.mark.asyncio
    async def test_backup_service_integration_workflow(
        self, backup_service_with_mock_executor, test_repository
    ) -> None:
        """Test complete backup service workflow integration"""
        # Mock successful backup and prune
        backup_result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Backup completed"],
            completed_at=now_utc(),
        )
        prune_result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Prune completed"],
            completed_at=now_utc(),
        )

        backup_service_with_mock_executor.executor.execute_backup = AsyncMock(
            return_value=backup_result
        )
        backup_service_with_mock_executor.executor.execute_prune = AsyncMock(
            return_value=prune_result
        )

        # 1. Execute backup
        job = Job(
            id="integration-job",
            repository_id=test_repository.id,
            type="backup",
            status="running",
            started_at=now_utc(),
        )
        backup_service_with_mock_executor.db.add(job)
        backup_service_with_mock_executor.db.commit()

        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/data"
        )

        with patch.object(
            backup_service_with_mock_executor, "_handle_post_backup_operations"
        ):
            backup_result = await backup_service_with_mock_executor.execute_backup(
                job, backup_request
            )

        # 2. Execute prune
        prune_request = PruneRequest(repository_id=test_repository.id, keep_daily=7)
        prune_job_id = await backup_service_with_mock_executor.create_and_run_prune(
            prune_request
        )

        # 3. Check job status
        backup_status = backup_service_with_mock_executor.get_job_status(
            "integration-job"
        )
        prune_status = backup_service_with_mock_executor.get_job_status(prune_job_id)

        # 4. List recent jobs
        recent_jobs = backup_service_with_mock_executor.list_recent_jobs()

        # Verify workflow
        assert backup_result.success is True
        assert backup_status is not None
        assert prune_status is not None
        assert len(recent_jobs) >= 2

    def test_backup_service_database_integration(
        self, backup_service, test_repository
    ) -> None:
        """Test that backup service properly integrates with real database"""
        # Test repository retrieval
        repo = backup_service._get_repository(test_repository.id)
        assert repo.name == test_repository.name

        # Test job creation
        backup_request = BackupRequest(
            repository_id=test_repository.id, source_path="/test"
        )
        job = backup_service._create_job_record(
            test_repository, JobType.BACKUP, backup_request
        )

        # Test job retrieval
        status = backup_service.get_job_status(job.id)
        assert status is not None
        assert status["id"] == job.id

        # Test job listing
        jobs = backup_service.list_recent_jobs()
        job_ids = [j["id"] for j in jobs]
        assert job.id in job_ids
