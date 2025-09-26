"""
Tests for ignore_lock functionality in backup operations.

This module tests that the borg break-lock command is executed when
the ignore_lock parameter is set to True in backup requests.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from borgitory.services.jobs.job_manager import (
    JobManager,
    JobManagerDependencies,
    BorgJob,
    BorgJobTask,
)
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.utils.datetime_utils import now_utc


class TestIgnoreLockFunctionality:
    """Test suite for ignore_lock functionality"""

    @pytest.fixture
    def mock_dependencies(self) -> JobManagerDependencies:
        """Create mock dependencies for JobManager"""
        deps = JobManagerDependencies()
        mock_executor = MagicMock()
        mock_executor.start_process = AsyncMock()
        mock_executor.monitor_process_output = AsyncMock()
        deps.job_executor = mock_executor

        deps.output_manager = MagicMock()
        deps.output_manager.add_output_line = AsyncMock()
        deps.event_broadcaster = MagicMock()

        return deps

    @pytest.fixture
    def job_manager(self, mock_dependencies: JobManagerDependencies) -> JobManager:
        """Create JobManager instance with mocked dependencies"""
        manager = JobManager(dependencies=mock_dependencies)
        # Ensure the executor is properly set and not None
        assert mock_dependencies.job_executor is not None
        manager.executor = mock_dependencies.job_executor
        return manager

    @pytest.fixture
    def mock_job(self) -> BorgJob:
        """Create a mock job for testing"""
        job = BorgJob(
            id="test-job-123",
            job_type="manual_backup",
            repository_id=1,
            status="running",
            started_at=now_utc(),
        )
        return job

    @pytest.fixture
    def mock_backup_task_with_ignore_lock(self) -> BorgJobTask:
        """Create a mock backup task with ignore_lock=True"""
        task = BorgJobTask(
            task_type="backup",
            task_name="Test Backup with Ignore Lock",
            parameters={
                "source_path": "/test/source",
                "compression": "zstd",
                "dry_run": False,
                "ignore_lock": True,
                "archive_name": "test-backup-20240101-120000",
            },
        )
        task.output_lines = []
        return task

    @pytest.fixture
    def mock_backup_task_without_ignore_lock(self) -> BorgJobTask:
        """Create a mock backup task with ignore_lock=False"""
        task = BorgJobTask(
            task_type="backup",
            task_name="Test Backup without Ignore Lock",
            parameters={
                "source_path": "/test/source",
                "compression": "zstd",
                "dry_run": False,
                "ignore_lock": False,
                "archive_name": "test-backup-20240101-120000",
            },
        )
        task.output_lines = []
        return task

    @pytest.fixture
    def mock_repository_data(self) -> Dict[str, Any]:
        """Mock repository data"""
        return {"path": "/test/repo/path", "passphrase": "test-passphrase"}

    @pytest.mark.asyncio
    async def test_ignore_lock_true_executes_break_lock_command(
        self,
        job_manager: JobManager,
        mock_job: BorgJob,
        mock_backup_task_with_ignore_lock: BorgJobTask,
        mock_repository_data: Dict[str, Any],
    ) -> None:
        """Test that borg break-lock is executed when ignore_lock=True"""

        # Mock process execution for the main backup command
        mock_process = MagicMock()
        mock_process.pid = 12345
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        # Mock process monitoring to return successful result
        mock_result = ProcessResult(
            return_code=0,
            stdout=b"Backup completed successfully",
            stderr=b"",
            error=None,
        )
        job_manager.executor.monitor_process_output.return_value = mock_result  # type: ignore

        # Execute the backup task with mocked methods
        with patch.object(
            job_manager, "_get_repository_data", return_value=mock_repository_data
        ), patch.object(job_manager, "_execute_break_lock") as mock_break_lock:
            result = await job_manager._execute_backup_task(
                mock_job, mock_backup_task_with_ignore_lock, task_index=0
            )

            # Verify that break-lock was called
            mock_break_lock.assert_called_once()
            call_args = mock_break_lock.call_args

            # Check the arguments passed to break-lock
            assert call_args[0][0] == "/test/repo/path"  # repository_path
            assert call_args[0][1] == "test-passphrase"  # passphrase
            assert callable(call_args[0][2])  # output_callback

        # Verify the backup task completed successfully
        assert result is True
        assert mock_backup_task_with_ignore_lock.status == "completed"

    @pytest.mark.asyncio
    async def test_ignore_lock_false_skips_break_lock_command(
        self,
        job_manager: JobManager,
        mock_job: BorgJob,
        mock_backup_task_without_ignore_lock: BorgJobTask,
        mock_repository_data: Dict[str, Any],
    ) -> None:
        """Test that borg break-lock is NOT executed when ignore_lock=False"""

        # Mock process execution for the main backup command
        mock_process = MagicMock()
        mock_process.pid = 12345
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        # Mock process monitoring to return successful result
        mock_result = ProcessResult(
            return_code=0,
            stdout=b"Backup completed successfully",
            stderr=b"",
            error=None,
        )
        job_manager.executor.monitor_process_output.return_value = mock_result  # type: ignore

        # Execute the backup task with mocked methods
        with patch.object(
            job_manager, "_get_repository_data", return_value=mock_repository_data
        ), patch.object(job_manager, "_execute_break_lock") as mock_break_lock:
            result = await job_manager._execute_backup_task(
                mock_job, mock_backup_task_without_ignore_lock, task_index=0
            )

            # Verify that break-lock was NOT called
            mock_break_lock.assert_not_called()

        # Verify the backup task completed successfully
        assert result is True
        assert mock_backup_task_without_ignore_lock.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_break_lock_command_construction(
        self, job_manager: JobManager
    ) -> None:
        """Test that _execute_break_lock builds the correct borg command"""

        # Mock the executor methods
        mock_process = MagicMock()
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        mock_result = ProcessResult(
            return_code=0, stdout=b"Lock successfully removed", stderr=b"", error=None
        )
        job_manager.executor.monitor_process_output.return_value = mock_result  # type: ignore

        # Mock output callback
        output_callback = MagicMock()

        # Test parameters
        repository_path = "/test/repo/path"
        passphrase = "test-passphrase"

        # Execute break-lock
        await job_manager._execute_break_lock(
            repository_path, passphrase, output_callback
        )

        # Verify start_process was called with correct command
        job_manager.executor.start_process.assert_called_once()  # type: ignore
        call_args = job_manager.executor.start_process.call_args  # type: ignore

        command = call_args[0][0]  # First positional argument is the command
        env = call_args[0][1]  # Second positional argument is the environment

        # Verify the command structure
        assert command[0] == "borg"
        assert command[1] == "break-lock"
        # Path might be converted to Windows format, so check if it contains the repo path
        assert any(
            repository_path in arg or repository_path.replace("/", "\\") in arg
            for arg in command
        )

        # Verify environment contains passphrase
        assert "BORG_PASSPHRASE" in env
        assert env["BORG_PASSPHRASE"] == passphrase

        # Verify output callback was called with expected messages
        output_callback.assert_any_call(
            "Running 'borg break-lock' to remove stale repository locks..."
        )
        output_callback.assert_any_call("Successfully released repository lock")

    @pytest.mark.asyncio
    async def test_break_lock_failure_continues_with_backup(
        self,
        job_manager: JobManager,
        mock_job: BorgJob,
        mock_backup_task_with_ignore_lock: BorgJobTask,
        mock_repository_data: Dict[str, Any],
    ) -> None:
        """Test that backup continues even if break-lock fails"""

        # Mock process execution for the main backup command
        mock_process = MagicMock()
        mock_process.pid = 12345
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        # Mock process monitoring to return successful result
        mock_result = ProcessResult(
            return_code=0,
            stdout=b"Backup completed successfully",
            stderr=b"",
            error=None,
        )
        job_manager.executor.monitor_process_output.return_value = mock_result  # type: ignore

        # Execute the backup task with mocked methods
        with patch.object(
            job_manager, "_get_repository_data", return_value=mock_repository_data
        ), patch.object(
            job_manager,
            "_execute_break_lock",
            side_effect=Exception("Break-lock failed"),
        ) as mock_break_lock:
            result = await job_manager._execute_backup_task(
                mock_job, mock_backup_task_with_ignore_lock, task_index=0
            )

            # Verify that break-lock was attempted
            mock_break_lock.assert_called_once()

        # Verify the backup task still completed successfully despite break-lock failure
        assert result is True
        assert mock_backup_task_with_ignore_lock.status == "completed"

        # Verify warning message was added to output
        output_lines = mock_backup_task_with_ignore_lock.output_lines
        warning_found = any("Break-lock failed" in line for line in output_lines)
        assert warning_found, f"Expected break-lock warning in output: {output_lines}"

    @pytest.mark.asyncio
    async def test_break_lock_timeout_handling(self, job_manager: JobManager) -> None:
        """Test that break-lock handles timeout correctly"""

        # Mock the executor methods
        mock_process = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        # Mock monitor_process_output to timeout
        async def mock_monitor_timeout(*args: Any, **kwargs: Any) -> None:
            await asyncio.sleep(0.1)  # Small delay to simulate work
            raise asyncio.TimeoutError()

        job_manager.executor.monitor_process_output = AsyncMock(
            side_effect=mock_monitor_timeout
        )  # type: ignore

        # Mock output callback
        output_callback = MagicMock()

        # Test parameters
        repository_path = "/test/repo/path"
        passphrase = "test-passphrase"

        # Execute break-lock and expect timeout exception
        with pytest.raises(Exception, match="Break-lock operation timed out"):
            await job_manager._execute_break_lock(
                repository_path, passphrase, output_callback
            )

        # Verify process was killed
        mock_process.kill.assert_called_once()
        mock_process.wait.assert_called_once()

        # Verify timeout message was sent to callback
        output_callback.assert_any_call("Break-lock timed out, terminating process")

    @pytest.mark.asyncio
    async def test_break_lock_uses_secure_command_builder(
        self, job_manager: JobManager
    ) -> None:
        """Test that break-lock executes the correct command through the executor"""

        # Mock the executor methods
        mock_process = MagicMock()
        job_manager.executor.start_process.return_value = mock_process  # type: ignore

        mock_result = ProcessResult(
            return_code=0, stdout=b"Success", stderr=b"", error=None
        )
        job_manager.executor.monitor_process_output.return_value = mock_result  # type: ignore

        # Execute break-lock
        await job_manager._execute_break_lock("/test/repo", "test-pass", MagicMock())

        # Verify executor was called with a borg break-lock command
        job_manager.executor.start_process.assert_called_once()
        call_args = job_manager.executor.start_process.call_args
        command = call_args[0][0]  # First positional argument
        env = call_args[0][1]  # Second positional argument

        # Verify it's a borg break-lock command
        assert "borg" in command[0]
        assert "break-lock" in command
        assert "BORG_PASSPHRASE" in env
