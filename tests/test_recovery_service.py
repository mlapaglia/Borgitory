"""
Tests for RecoveryService - Recovery and cleanup functionality tests
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
def recovery_service(
    mock_command_executor: Mock, mock_session_maker: Mock
) -> RecoveryService:
    """Create RecoveryService with mock command executor."""
    return RecoveryService(
        command_executor=mock_command_executor, session_maker=mock_session_maker
    )


@pytest.fixture
def mock_session_maker() -> Mock:
    """Create mock session maker."""
    return Mock(spec=async_sessionmaker[AsyncSession])


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

    def test_service_initialization(
        self, mock_command_executor: Mock, mock_session_maker: Mock
    ) -> None:
        """Test RecoveryService initializes correctly with command executor."""
        service = RecoveryService(
            command_executor=mock_command_executor, session_maker=mock_session_maker
        )
        assert service.command_executor is mock_command_executor

    async def test_recover_stale_jobs(self, recovery_service: RecoveryService) -> None:
        """Test the main recovery entry point."""
        with patch.object(
            recovery_service, "recover_database_job_records", new_callable=AsyncMock
        ) as mock_recover:
            await recovery_service.recover_stale_jobs()
            mock_recover.assert_called_once()


class TestRecoveryServiceDatabaseRecovery:
    """Test database job record recovery."""

    async def test_recover_database_job_records_no_interrupted_jobs(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test recovery when no interrupted jobs exist."""
        # Create mock async session
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # Mock the session maker context manager
        mock_session_context = Mock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)

        recovery_service.session_maker.return_value = mock_session_context

        # Should complete without error
        await recovery_service.recover_database_job_records()

        # Verify execute was called
        mock_db.execute.assert_called_once()

    async def test_recover_database_job_records_with_interrupted_jobs(
        self, recovery_service: RecoveryService, mock_repository: Mock
    ) -> None:
        """Test recovery with interrupted jobs."""
        # Create mock async session
        mock_db = AsyncMock(spec=AsyncSession)

        # Create mock interrupted job
        mock_job = Mock()
        mock_job.id = 1
        mock_job.job_type = "manual_backup"
        mock_job.repository_id = 1
        mock_job.started_at = datetime.now()
        mock_job.tasks = []

        # Create mock interrupted task
        mock_task = Mock()
        mock_task.task_name = "backup_task"

        # Mock the queries - there are 3 queries:
        # 1. Query for interrupted jobs
        mock_job_result = Mock()
        mock_job_result.scalars.return_value.all.return_value = [mock_job]

        # 2. Query for running tasks of the job
        mock_task_result = Mock()
        mock_task_result.scalars.return_value.all.return_value = [mock_task]

        # 3. Query for the repository
        mock_repo_result = Mock()
        mock_repo_result.scalar_one_or_none.return_value = mock_repository

        # Set up execute to return different results for different queries
        mock_db.execute.side_effect = [
            mock_job_result,
            mock_task_result,
            mock_repo_result,
        ]

        # Mock the session maker context manager
        mock_session_context = Mock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        recovery_service.session_maker.return_value = mock_session_context

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

    async def test_recover_database_job_records_non_backup_job(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test recovery with non-backup job types."""
        # Create mock async session
        mock_db = AsyncMock(spec=AsyncSession)

        # Create mock non-backup job
        mock_job = Mock()
        mock_job.id = 1
        mock_job.job_type = "scan"  # Not a backup job
        mock_job.repository_id = None
        mock_job.started_at = datetime.now()
        mock_job.tasks = []

        # Mock the queries
        mock_job_result = Mock()
        mock_job_result.scalars.return_value.all.return_value = [mock_job]
        mock_db.execute.return_value = mock_job_result

        # Mock the session maker context manager
        mock_session_context = Mock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        recovery_service.session_maker.return_value = mock_session_context

        with patch.object(
            recovery_service, "_release_repository_lock", new_callable=AsyncMock
        ) as mock_release:
            await recovery_service.recover_database_job_records()

            # Verify job was marked as failed
            assert mock_job.status == "failed"

            # Verify repository lock was NOT released (not a backup job)
            mock_release.assert_not_called()

    async def test_recover_database_job_records_exception_handling(
        self, recovery_service: RecoveryService
    ) -> None:
        """Test exception handling during database recovery."""
        # Make the session maker raise an exception
        recovery_service.session_maker.side_effect = Exception("Database error")

        # Should not raise exception, just log it
        await recovery_service.recover_database_job_records()


class TestRecoveryServiceLockRelease:
    """Test repository lock release functionality."""

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
            "borgitory.services.recovery_service.create_borg_command"
        ) as mock_secure:
            # Create mock borg command object with command and environment attributes
            mock_borg_command = Mock()
            mock_borg_command.command = ["borg", "break-lock", "/test/repo/path"]
            mock_borg_command.environment = {"BORG_PASSPHRASE": "test-passphrase"}
            mock_secure.return_value = mock_borg_command

            # Should complete without raising exception
            await recovery_service._release_repository_lock(mock_repository)

            # Verify the command executor was called
            mock_command_executor.create_subprocess.assert_called_once()
            call_args = mock_command_executor.create_subprocess.call_args

            # Verify the command contains expected elements
            assert call_args[1]["command"] == ["borg", "break-lock", "/test/repo/path"]
            assert "BORG_PASSPHRASE" in call_args[1]["env"]

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
            "borgitory.services.recovery_service.create_borg_command"
        ) as mock_secure:
            # Create mock borg command object with command and environment attributes
            mock_borg_command = Mock()
            mock_borg_command.command = ["borg", "break-lock", "/test/repo/path"]
            mock_borg_command.environment = {"BORG_PASSPHRASE": "test-passphrase"}
            mock_secure.return_value = mock_borg_command

            # Should complete without raising exception (just logs warning)
            await recovery_service._release_repository_lock(mock_repository)

            # Verify the command executor was called
            mock_command_executor.create_subprocess.assert_called_once()

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
            "borgitory.services.recovery_service.create_borg_command"
        ) as mock_secure:
            # Create mock borg command object with command and environment attributes
            mock_borg_command = Mock()
            mock_borg_command.command = ["borg", "break-lock", "/test/repo/path"]
            mock_borg_command.environment = {"BORG_PASSPHRASE": "test-passphrase"}
            mock_secure.return_value = mock_borg_command

            # Should complete without raising exception (handles timeout)
            await recovery_service._release_repository_lock(mock_repository)

            # Verify process was killed
            mock_process.kill.assert_called_once()

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
            "borgitory.services.recovery_service.create_borg_command"
        ) as mock_secure:
            # Create mock borg command object with command and environment attributes
            mock_borg_command = Mock()
            mock_borg_command.command = ["borg", "break-lock", "/test/repo/path"]
            mock_borg_command.environment = {"BORG_PASSPHRASE": "test-passphrase"}
            mock_secure.return_value = mock_borg_command

            # Should complete without raising exception (logs error)
            await recovery_service._release_repository_lock(mock_repository)


class TestRecoveryServiceIntegration:
    """Test integration scenarios."""

    async def test_full_recovery_workflow(
        self,
        recovery_service: RecoveryService,
        mock_command_executor: Mock,
        mock_session_maker: Mock,
    ) -> None:
        """Test the complete recovery workflow."""
        with patch.object(
            recovery_service, "recover_database_job_records", new_callable=AsyncMock
        ) as mock_recover:
            await recovery_service.recover_stale_jobs()

            # Verify the database recovery was called
            mock_recover.assert_called_once()

    def test_dependency_injection_pattern(
        self, mock_command_executor: Mock, mock_session_maker: Mock
    ) -> None:
        """Test that RecoveryService follows proper dependency injection patterns."""
        # Should be able to create multiple instances with different dependencies
        service1 = RecoveryService(
            command_executor=mock_command_executor, session_maker=mock_session_maker
        )

        other_command_executor = Mock(spec=CommandExecutorProtocol)
        service2 = RecoveryService(
            command_executor=other_command_executor, session_maker=mock_session_maker
        )

        # Services should have different command executors
        assert service1.command_executor is not service2.command_executor
        assert service1.command_executor is mock_command_executor
        assert service2.command_executor is other_command_executor
