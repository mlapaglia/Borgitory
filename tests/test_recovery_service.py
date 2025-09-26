"""
Tests for RecoveryService - Service for handling crashed or interrupted backup jobs
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from borgitory.services.recovery_service import RecoveryService
from borgitory.models.database import Repository, Job, JobTask


@pytest.fixture
def recovery_service():
    return RecoveryService()


@pytest.fixture
def mock_repository():
    """Mock repository object"""
    repo = MagicMock(spec=Repository)
    repo.id = 1
    repo.name = "test-repo"
    repo.path = "/repo/path"
    repo.get_passphrase.return_value = "test_passphrase"
    repo.get_keyfile_content.return_value = None
    return repo


@pytest.fixture
def mock_job():
    """Mock job object"""
    job = MagicMock(spec=Job)
    job.id = 123
    job.job_type = "manual_backup"
    job.status = "running"
    job.repository_id = 1
    job.started_at = datetime(2023, 1, 1, 12, 0, 0)
    return job


@pytest.fixture
def mock_task():
    """Mock job task object"""
    task = MagicMock(spec=JobTask)
    task.id = 456
    task.job_id = 123
    task.task_name = "backup_create"
    task.status = "running"
    return task


class TestRecoveryService:
    """Test the RecoveryService class"""

    @pytest.mark.asyncio
    async def test_recover_stale_jobs(self, recovery_service) -> None:
        """Test the main recovery method"""
        with patch.object(
            recovery_service, "recover_database_job_records"
        ) as mock_recover:
            await recovery_service.recover_stale_jobs()

            mock_recover.assert_called_once()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_no_interrupted_jobs(
        self, recovery_service
    ) -> None:
        """Test recovery when no interrupted jobs exist"""
        mock_db = MagicMock()

        # Mock query to return no interrupted jobs
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should query for running/pending jobs
            mock_db.query.assert_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_with_interrupted_jobs(
        self, recovery_service, mock_job, mock_task, mock_repository
    ) -> None:
        """Test recovery with interrupted jobs"""
        mock_db = MagicMock()

        # Mock query to return interrupted job
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [mock_job],  # First call returns interrupted jobs
            [mock_task],  # Second call returns running tasks
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_repository
        )

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session, patch.object(
            recovery_service, "_release_repository_lock"
        ) as mock_release_lock:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should mark job as failed
            assert mock_job.status == "failed"
            assert mock_job.finished_at is not None
            assert "Job cancelled on startup" in mock_job.error

            # Should mark task as failed
            assert mock_task.status == "failed"
            assert mock_task.completed_at is not None
            assert "Task cancelled on startup" in mock_task.error

            # Should release repository lock
            mock_release_lock.assert_called_once_with(mock_repository)

    @pytest.mark.asyncio
    async def test_recover_database_job_records_non_backup_job(
        self, recovery_service
    ) -> None:
        """Test recovery with non-backup job (no lock release needed)"""
        mock_db = MagicMock()

        # Create non-backup job
        non_backup_job = MagicMock(spec=Job)
        non_backup_job.id = 123
        non_backup_job.job_type = "list_archives"  # Not a backup job
        non_backup_job.status = "running"
        non_backup_job.repository_id = 1
        non_backup_job.started_at = datetime(2023, 1, 1, 12, 0, 0)

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [non_backup_job],  # Interrupted jobs
            [],  # No running tasks
        ]

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session, patch.object(
            recovery_service, "_release_repository_lock"
        ) as mock_release_lock:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should mark job as failed but not release lock
            assert non_backup_job.status == "failed"
            mock_release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_backup_job_no_repository(
        self, recovery_service
    ) -> None:
        """Test recovery with backup job but no repository found"""
        mock_db = MagicMock()

        backup_job = MagicMock(spec=Job)
        backup_job.id = 123
        backup_job.job_type = "manual_backup"
        backup_job.status = "running"
        backup_job.repository_id = 999  # Non-existent repository
        backup_job.started_at = datetime(2023, 1, 1, 12, 0, 0)

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [backup_job],  # Interrupted jobs
            [],  # No running tasks
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = (
            None  # Repository not found
        )

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session, patch.object(
            recovery_service, "_release_repository_lock"
        ) as mock_release_lock:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should mark job as failed but not release lock since repo not found
            assert backup_job.status == "failed"
            mock_release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_multiple_job_types(
        self, recovery_service
    ) -> None:
        """Test recovery with different backup job types"""
        mock_db = MagicMock()

        # Create different backup job types (removed "composite" since it's no longer a separate type)
        manual_job = MagicMock(spec=Job)
        manual_job.job_type = "manual_backup"
        manual_job.repository_id = 1

        scheduled_job = MagicMock(spec=Job)
        scheduled_job.job_type = "scheduled_backup"
        scheduled_job.repository_id = 2

        prune_job = MagicMock(spec=Job)
        prune_job.job_type = "prune"
        prune_job.repository_id = 3

        for job in [manual_job, scheduled_job, prune_job]:
            job.id = 123
            job.status = "running"
            job.started_at = datetime(2023, 1, 1, 12, 0, 0)

        mock_repository = MagicMock(spec=Repository)
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [manual_job, scheduled_job, prune_job],  # Interrupted jobs
            [],
            [],
            [],  # No running tasks for each job
        ]
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_repository
        )

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session, patch.object(
            recovery_service, "_release_repository_lock"
        ) as mock_release_lock:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should release locks for backup job types only (not prune)
            assert mock_release_lock.call_count == 2

    @pytest.mark.asyncio
    async def test_recover_database_job_records_exception_handling(
        self, recovery_service
    ) -> None:
        """Test exception handling in database job recovery"""
        with patch(
            "borgitory.services.recovery_service.get_db_session",
            side_effect=Exception("Database error"),
        ):
            # Should not raise exception
            await recovery_service.recover_database_job_records()

    @pytest.mark.asyncio
    async def test_release_repository_lock_success(
        self, recovery_service, mock_repository
    ) -> None:
        """Test successful repository lock release"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Lock released", b""))

        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            return_value=(
                ["borg", "break-lock", "/repo/path"],
                {"BORG_PASSPHRASE": "test"},
            ),
        ), patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await recovery_service._release_repository_lock(mock_repository)

            # Should build secure command with correct parameters
            assert mock_repository.get_passphrase.called

    @pytest.mark.asyncio
    async def test_release_repository_lock_command_failure(
        self, recovery_service, mock_repository
    ) -> None:
        """Test repository lock release with command failure"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Lock not found"))

        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            return_value=(
                ["borg", "break-lock", "/repo/path"],
                {"BORG_PASSPHRASE": "test"},
            ),
        ), patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception even on command failure
            await recovery_service._release_repository_lock(mock_repository)

    @pytest.mark.asyncio
    async def test_release_repository_lock_timeout(
        self, recovery_service, mock_repository
    ) -> None:
        """Test repository lock release with timeout"""
        mock_process = MagicMock()
        mock_process.kill = MagicMock()

        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            return_value=(
                ["borg", "break-lock", "/repo/path"],
                {"BORG_PASSPHRASE": "test"},
            ),
        ), patch("asyncio.create_subprocess_exec", return_value=mock_process), patch(
            "asyncio.wait_for", side_effect=asyncio.TimeoutError()
        ):
            # Should handle timeout gracefully
            await recovery_service._release_repository_lock(mock_repository)

            # Should kill the process
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_repository_lock_exception(
        self, recovery_service, mock_repository
    ) -> None:
        """Test repository lock release with exception"""
        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            side_effect=Exception("Command build failed"),
        ):
            # Should handle exception gracefully
            await recovery_service._release_repository_lock(mock_repository)

    @pytest.mark.asyncio
    async def test_release_repository_lock_no_stderr(
        self, recovery_service, mock_repository
    ) -> None:
        """Test repository lock release with no stderr output"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", None))  # No stderr

        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            return_value=(
                ["borg", "break-lock", "/repo/path"],
                {"BORG_PASSPHRASE": "test"},
            ),
        ), patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await recovery_service._release_repository_lock(mock_repository)

    @pytest.mark.asyncio
    async def test_recover_database_job_records_job_without_repository_id(
        self, recovery_service
    ) -> None:
        """Test recovery with backup job but no repository_id"""
        mock_db = MagicMock()

        backup_job = MagicMock(spec=Job)
        backup_job.id = 123
        backup_job.job_type = "manual_backup"
        backup_job.status = "running"
        backup_job.repository_id = None  # No repository ID
        backup_job.started_at = datetime(2023, 1, 1, 12, 0, 0)

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [backup_job],  # Interrupted jobs
            [],  # No running tasks
        ]

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session, patch.object(
            recovery_service, "_release_repository_lock"
        ) as mock_release_lock:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None

            await recovery_service.recover_database_job_records()

            # Should mark job as failed but not try to release lock
            assert backup_job.status == "failed"
            mock_release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_multiple_task_statuses(
        self, recovery_service
    ) -> None:
        """Test recovery with tasks in different statuses"""
        mock_db = MagicMock()

        job = MagicMock(spec=Job)
        job.id = 123
        job.job_type = "utility"  # Non-backup job
        job.status = "running"
        job.started_at = datetime(2023, 1, 1, 12, 0, 0)

        # Create tasks with different statuses
        pending_task = MagicMock(spec=JobTask)
        pending_task.task_name = "pending_task"
        pending_task.status = "pending"

        running_task = MagicMock(spec=JobTask)
        running_task.task_name = "running_task"
        running_task.status = "running"

        in_progress_task = MagicMock(spec=JobTask)
        in_progress_task.task_name = "in_progress_task"
        in_progress_task.status = "in_progress"

        completed_task = MagicMock(spec=JobTask)
        completed_task.task_name = "completed_task"
        completed_task.status = "completed"  # Should not be affected

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [job],  # Interrupted jobs
            [
                pending_task,
                running_task,
                in_progress_task,
            ],  # Only incomplete tasks returned by query
        ]

        with patch(
            "borgitory.services.recovery_service.get_db_session"
        ) as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db
            mock_get_session.return_value.__exit__.return_value = None
            await recovery_service.recover_database_job_records()

            # Should mark all incomplete tasks as failed
            assert pending_task.status == "failed"
            assert running_task.status == "failed"
            assert in_progress_task.status == "failed"

            # Completed task should not be queried/modified
            assert completed_task.status == "completed"
