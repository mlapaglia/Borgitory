"""
Tests for RecoveryService - Recovery and cleanup functionality tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from borgitory.services.recovery_service import RecoveryService
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.models.database import Repository


@pytest.fixture
def mock_command_executor() -> Mock:
    """Create mock command executor."""
    mock = Mock(spec=CommandExecutorProtocol)
    mock.create_subprocess = AsyncMock()
    mock.execute_command = AsyncMock()
    return mock


@pytest.fixture
def recovery_service(mock_command_executor: Mock) -> RecoveryService:
    """Create RecoveryService with mock command executor."""
    return RecoveryService(command_executor=mock_command_executor)


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock repository."""
    repo = Mock(spec=Repository)
    repo.name = "test-repo"
    repo.path = "/test/repo/path"
    repo.get_passphrase.return_value = "test-passphrase"
    repo.get_keyfile_content.return_value = None
    return repo


class TestRecoveryServiceBasics:
    """Test basic RecoveryService functionality."""

    def test_service_initialization(self, mock_command_executor: Mock) -> None:
        """Test RecoveryService initializes correctly with command executor."""
        service = RecoveryService(command_executor=mock_command_executor)
        assert service.command_executor is mock_command_executor

    @pytest.mark.asyncio
    async def test_recover_stale_jobs(self, recovery_service: RecoveryService) -> None:
        """Test the main recovery entry point."""
        with patch.object(
            recovery_service, "recover_database_job_records", new_callable=AsyncMock
        ) as mock_recover:
            await recovery_service.recover_stale_jobs()
            mock_recover.assert_called_once()


class TestRecoveryServiceDatabaseRecovery:
    """Test database job record recovery."""

    @pytest.mark.asyncio
    async def test_recover_database_job_records_no_interrupted_jobs(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test recovery when no interrupted jobs exist."""
        with patch("borgitory.services.recovery_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            # Mock query to return no interrupted jobs
            mock_db.query.return_value.filter.return_value.all.return_value = []

            # Should complete without error
            await recovery_service.recover_database_job_records()

            # Verify query was called
            mock_db.query.assert_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_with_interrupted_jobs(
        self, recovery_service: RecoveryService, mock_repository: Mock
    ) -> None:
        """Test recovery with interrupted jobs."""
        with patch("borgitory.services.recovery_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            # Create mock interrupted job
            mock_job = Mock()
            mock_job.id = 1
            mock_job.job_type = "manual_backup"
            mock_job.repository_id = 1
            mock_job.started_at = datetime.now()

            # Create mock interrupted task
            mock_task = Mock()
            mock_task.task_name = "backup_task"

            # Mock queries
            mock_db.query.return_value.filter.return_value.all.side_effect = [
                [mock_job],  # First call returns interrupted jobs
                [mock_task],  # Second call returns interrupted tasks
            ]
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_repository
            )

            with patch.object(
                recovery_service, "_release_repository_lock", new_callable=AsyncMock
            ) as mock_release:
                await recovery_service.recover_database_job_records()

                # Verify job was marked as failed
                assert mock_job.status == "failed"
                assert mock_job.finished_at is not None
                assert "cancelled on startup" in mock_job.error.lower()

                # Verify task was marked as failed
                assert mock_task.status == "failed"
                assert mock_task.completed_at is not None
                assert "cancelled on startup" in mock_task.error.lower()

                # Verify repository lock was released
                mock_release.assert_called_once_with(mock_repository)

    @pytest.mark.asyncio
    async def test_recover_database_job_records_non_backup_job(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test recovery with non-backup job types."""
        with patch("borgitory.services.recovery_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            # Create mock non-backup job
            mock_job = Mock()
            mock_job.id = 1
            mock_job.job_type = "scan"  # Not a backup job
            mock_job.repository_id = None
            mock_job.started_at = datetime.now()

            # Mock queries
            mock_db.query.return_value.filter.return_value.all.side_effect = [
                [mock_job],  # First call returns interrupted jobs
                [],  # Second call returns no interrupted tasks
            ]

            with patch.object(
                recovery_service, "_release_repository_lock", new_callable=AsyncMock
            ) as mock_release:
                await recovery_service.recover_database_job_records()

                # Verify job was marked as failed
                assert mock_job.status == "failed"

                # Verify repository lock was NOT released (not a backup job)
                mock_release.assert_not_called()

    @pytest.mark.asyncio
    async def test_recover_database_job_records_exception_handling(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test exception handling during database recovery."""
        with patch("borgitory.services.recovery_service.get_db_session") as mock_get_db:
            mock_get_db.side_effect = Exception("Database error")

            # Should not raise exception, just log it
            await recovery_service.recover_database_job_records()


class TestRecoveryServiceLockRelease:
    """Test repository lock release functionality."""

    @pytest.mark.asyncio
    async def test_release_repository_lock_success(
        self,
        recovery_service: RecoveryService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test successful repository lock release."""
        # Mock subprocess for break-lock command
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Lock released", b""))
        mock_command_executor.create_subprocess.return_value = mock_process

        with patch(
            "borgitory.services.recovery_service.secure_borg_command"
        ) as mock_secure:
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "break-lock", "/test/repo/path"],
                {"BORG_PASSPHRASE": "test-passphrase"},
                None,
            )

            # Should complete without raising exception
            await recovery_service._release_repository_lock(mock_repository)

            # Verify the command executor was called
            mock_command_executor.create_subprocess.assert_called_once()
            call_args = mock_command_executor.create_subprocess.call_args

            # Verify the command contains expected elements
            assert call_args[1]["command"] == ["borg", "break-lock", "/test/repo/path"]
            assert "BORG_PASSPHRASE" in call_args[1]["env"]

    @pytest.mark.asyncio
    async def test_release_repository_lock_command_failure(
        self,
        recovery_service: RecoveryService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test repository lock release when command fails."""
        # Mock subprocess that fails
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Lock not found"))
        mock_command_executor.create_subprocess.return_value = mock_process

        with patch(
            "borgitory.services.recovery_service.secure_borg_command"
        ) as mock_secure:
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "break-lock", "/test/repo/path"],
                {"BORG_PASSPHRASE": "test-passphrase"},
                None,
            )

            # Should complete without raising exception (just logs warning)
            await recovery_service._release_repository_lock(mock_repository)

            # Verify the command executor was called
            mock_command_executor.create_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_repository_lock_timeout(
        self,
        recovery_service: RecoveryService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test repository lock release timeout handling."""
        # Mock subprocess that times out
        mock_process = Mock()
        mock_process.kill = Mock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_command_executor.create_subprocess.return_value = mock_process

        with patch(
            "borgitory.services.recovery_service.secure_borg_command"
        ) as mock_secure:
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "break-lock", "/test/repo/path"],
                {"BORG_PASSPHRASE": "test-passphrase"},
                None,
            )

            # Should complete without raising exception (handles timeout)
            await recovery_service._release_repository_lock(mock_repository)

            # Verify process was killed
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_repository_lock_exception(
        self,
        recovery_service: RecoveryService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test repository lock release exception handling."""
        # Mock command executor to raise an exception
        mock_command_executor.create_subprocess.side_effect = Exception("Process error")

        with patch(
            "borgitory.services.recovery_service.secure_borg_command"
        ) as mock_secure:
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "break-lock", "/test/repo/path"],
                {"BORG_PASSPHRASE": "test-passphrase"},
                None,
            )

            # Should complete without raising exception (logs error)
            await recovery_service._release_repository_lock(mock_repository)


class TestRecoveryServiceIntegration:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_recovery_workflow(
        self, recovery_service: RecoveryService, mock_command_executor: Mock
    ) -> None:
        """Test the complete recovery workflow."""
        with patch.object(
            recovery_service, "recover_database_job_records", new_callable=AsyncMock
        ) as mock_recover:
            await recovery_service.recover_stale_jobs()

            # Verify the database recovery was called
            mock_recover.assert_called_once()

    def test_dependency_injection_pattern(self, mock_command_executor: Mock) -> None:
        """Test that RecoveryService follows proper dependency injection patterns."""
        # Should be able to create multiple instances with different dependencies
        service1 = RecoveryService(command_executor=mock_command_executor)

        other_command_executor = Mock(spec=CommandExecutorProtocol)
        service2 = RecoveryService(command_executor=other_command_executor)

        # Services should have different command executors
        assert service1.command_executor is not service2.command_executor
        assert service1.command_executor is mock_command_executor
        assert service2.command_executor is other_command_executor
