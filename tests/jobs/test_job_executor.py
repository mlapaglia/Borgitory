"""
Tests for JobExecutor - subprocess execution and process management
"""

import pytest
import asyncio
from typing import Dict
from unittest.mock import AsyncMock, patch

from borgitory.services.jobs.job_executor import JobExecutor


class TestJobExecutor:
    """Test JobExecutor functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.mock_subprocess = AsyncMock()
        self.executor = JobExecutor(subprocess_executor=self.mock_subprocess)

    @pytest.mark.asyncio
    async def test_start_process_success(self) -> None:
        """Test successful process start"""
        mock_process = AsyncMock()
        mock_process.pid = 12345
        self.mock_subprocess.return_value = mock_process

        command = ["borg", "list", "repo"]
        env = {"BORG_PASSPHRASE": "test"}

        process = await self.executor.start_process(command, env)

        assert process == mock_process
        self.mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_process_failure(self) -> None:
        """Test process start failure"""

        # Use AsyncMock side_effect properly to avoid unawaited coroutine warnings
        async def mock_failure(*args, **kwargs):
            raise Exception("Process start failed")

        self.mock_subprocess.side_effect = mock_failure

        command = ["borg", "list", "repo"]

        with pytest.raises(Exception, match="Process start failed"):
            await self.executor.start_process(command)

    @pytest.mark.asyncio
    async def test_monitor_process_output_success(self) -> None:
        """Test successful process output monitoring"""
        mock_process = AsyncMock()
        mock_process.wait.return_value = 0

        # Mock stdout lines
        async def mock_stdout():
            yield b"line1\n"
            yield b"line2\n"

        mock_process.stdout = mock_stdout()

        output_lines = []
        progress_updates = []

        def output_callback(line: str) -> None:
            output_lines.append(line)

        def progress_callback(progress: Dict[str, object]) -> None:
            progress_updates.append(progress)

        result = await self.executor.monitor_process_output(
            mock_process,
            output_callback=output_callback,
            progress_callback=progress_callback,
        )

        assert result.return_code == 0
        assert output_lines == ["line1", "line2"]
        assert result.error is None

    @pytest.mark.asyncio
    async def test_monitor_process_output_with_error(self) -> None:
        """Test process output monitoring with error"""
        mock_process = AsyncMock()
        mock_process.wait.return_value = 1
        mock_process.stdout = AsyncMock()
        mock_process.stdout.__aiter__.side_effect = Exception("Read error")

        result = await self.executor.monitor_process_output(mock_process)

        assert result.return_code == -1
        assert result.error is not None
        assert "Process monitoring error" in result.error

    def test_parse_progress_line_borg_output(self) -> None:
        """Test parsing Borg progress output"""
        line = "1000000 500000 300000 100 /path/to/file"

        progress = self.executor.parse_progress_line(line)

        assert progress["original_size"] == 1000000
        assert progress["compressed_size"] == 500000
        assert progress["deduplicated_size"] == 300000
        assert progress["nfiles"] == 100
        assert progress["path"] == "/path/to/file"
        assert "timestamp" in progress

    def test_parse_progress_line_archive_name(self) -> None:
        """Test parsing archive name line"""
        line = "Archive name: test-archive-2023"

        progress = self.executor.parse_progress_line(line)

        assert progress["archive_name"] == "test-archive-2023"

    def test_parse_progress_line_no_match(self) -> None:
        """Test parsing line with no progress info"""
        line = "Some random output line"

        progress = self.executor.parse_progress_line(line)

        assert progress == {}

    def test_parse_progress_line_invalid_format(self) -> None:
        """Test parsing malformed progress line"""
        line = "1000000 abc 300000 def /path"

        progress = self.executor.parse_progress_line(line)

        # Should not raise exception, just return empty dict
        assert progress == {}

    @pytest.mark.asyncio
    async def test_terminate_process_graceful(self) -> None:
        """Test graceful process termination"""
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.wait.return_value = 0

        result = await self.executor.terminate_process(mock_process, timeout=1.0)

        assert result is True
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_process_force_kill(self) -> None:
        """Test force killing process after timeout"""
        mock_process = AsyncMock()
        mock_process.returncode = None

        # Mock wait_for to timeout first time (graceful termination), succeed second time (after kill)
        with patch("asyncio.wait_for", side_effect=[asyncio.TimeoutError(), None]):
            result = await self.executor.terminate_process(mock_process, timeout=0.1)

        assert result is True
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_process_already_terminated(self) -> None:
        """Test terminating already finished process"""
        mock_process = AsyncMock()
        mock_process.returncode = 0  # Already finished

        result = await self.executor.terminate_process(mock_process)

        assert result is True
        mock_process.terminate.assert_not_called()
        mock_process.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_terminate_process_error(self) -> None:
        """Test error during process termination"""
        mock_process = AsyncMock()
        mock_process.returncode = None

        # Use a regular function that raises an exception, not an async mock
        def terminate_error():
            raise Exception("Termination error")

        mock_process.terminate = terminate_error

        result = await self.executor.terminate_process(mock_process)

        assert result is False

    def test_format_command_for_logging_basic(self) -> None:
        """Test basic command formatting"""
        command = ["borg", "list", "repo"]

        result = self.executor.format_command_for_logging(command)

        assert result == "borg list repo"

    def test_format_command_for_logging_with_passphrase(self) -> None:
        """Test command formatting with passphrase redaction"""
        command = ["borg", "list", "--passphrase", "secret123", "repo"]

        result = self.executor.format_command_for_logging(command)

        assert result == "borg list --passphrase [REDACTED] repo"
        assert "secret123" not in result

    def test_format_command_for_logging_with_repository_path(self) -> None:
        """Test command formatting with repository path"""
        command = ["borg", "create", "repo::archive-name", "/path"]

        result = self.executor.format_command_for_logging(command)

        assert result == "borg create repo::[ARCHIVE] /path"
        assert "archive-name" not in result
