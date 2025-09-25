"""
Tests for SimpleCommandRunner service
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.protocols.command_protocols import CommandResult
from borgitory.config.command_runner_config import CommandRunnerConfig


class TestSimpleCommandRunner:
    """Test class for SimpleCommandRunner."""

    @pytest.fixture
    def test_config(self) -> CommandRunnerConfig:
        """Create test configuration."""
        return CommandRunnerConfig(timeout=30, max_retries=1, log_commands=False)

    @pytest.fixture
    def runner(self, test_config: CommandRunnerConfig) -> SimpleCommandRunner:
        """Create SimpleCommandRunner instance for testing."""
        return SimpleCommandRunner(config=test_config)

    def test_initialization(self) -> None:
        """Test SimpleCommandRunner initialization."""
        default_config = CommandRunnerConfig()
        runner = SimpleCommandRunner(config=default_config)
        assert runner.timeout == 300  # Default timeout
        assert runner.max_retries == 3
        assert runner.log_commands is True

        custom_config = CommandRunnerConfig(
            timeout=60, max_retries=5, log_commands=False
        )
        runner_custom = SimpleCommandRunner(config=custom_config)
        assert runner_custom.timeout == 60
        assert runner_custom.max_retries == 5
        assert runner_custom.log_commands is False

    @pytest.mark.asyncio
    async def test_run_command_success(self, runner: SimpleCommandRunner) -> None:
        """Test successful command execution."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"output", b"")

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_process

            result = await runner.run_command(["echo", "test"])

            assert isinstance(result, CommandResult)
            assert result.success is True
            assert result.return_code == 0
            assert result.stdout == "output"
            assert result.stderr == ""
            assert result.duration > 0
            assert result.error is None

    @pytest.mark.asyncio
    async def test_run_command_failure(self, runner: SimpleCommandRunner) -> None:
        """Test failed command execution."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"error message")

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_process

            result = await runner.run_command(["false"])

            assert isinstance(result, CommandResult)
            assert result.success is False
            assert result.return_code == 1
            assert result.stdout == ""
            assert result.stderr == "error message"
            assert result.duration > 0
            assert result.error == "error message"

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, runner: SimpleCommandRunner) -> None:
        """Test command execution timeout."""
        mock_process = AsyncMock()
        mock_process.kill = Mock()
        mock_process.wait = AsyncMock()

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create, patch(
            "asyncio.wait_for", new_callable=AsyncMock
        ) as mock_wait:
            mock_create.return_value = mock_process
            mock_wait.side_effect = asyncio.TimeoutError()

            result = await runner.run_command(["sleep", "60"], timeout=1)

            assert isinstance(result, CommandResult)
            assert result.success is False
            assert result.return_code == -1
            assert result.stdout == ""
            assert "timed out after 1 seconds" in result.stderr
            assert result.duration > 0
            assert result.error is not None
            assert "timed out after 1 seconds" in result.error

            # Verify process was killed
            mock_process.kill.assert_called_once()
            mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_command_with_env(self, runner: SimpleCommandRunner) -> None:
        """Test command execution with environment variables."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"test_value", b"")

        env_vars = {"TEST_VAR": "test_value"}

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_process

            result = await runner.run_command(["env"], env=env_vars)

            assert result.success is True
            assert result.stdout == "test_value"

            # Verify subprocess was created with correct environment
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["env"] == env_vars

    @pytest.mark.asyncio
    async def test_run_command_custom_timeout(
        self, runner: SimpleCommandRunner
    ) -> None:
        """Test command execution with custom timeout override."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"output", b"")

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create, patch("asyncio.wait_for") as mock_wait:
            mock_create.return_value = mock_process
            mock_wait.return_value = (b"output", b"")

            result = await runner.run_command(["echo", "test"], timeout=60)

            assert result.success is True

            # Verify wait_for was called with custom timeout
            mock_wait.assert_called_once()
            call_args = mock_wait.call_args
            assert call_args[1]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_run_command_exception_during_creation(
        self, runner: SimpleCommandRunner
    ) -> None:
        """Test handling of exception during subprocess creation."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("Command not found")
        ):
            result = await runner.run_command(["nonexistent_command"])

            assert isinstance(result, CommandResult)
            assert result.success is False
            assert result.return_code == -1
            assert result.stdout == ""
            assert "Failed to execute command: Command not found" in result.stderr
            assert result.duration > 0
            assert result.error is not None
            assert "Failed to execute command: Command not found" in result.error

    @pytest.mark.asyncio
    async def test_run_command_with_binary_output(
        self, runner: SimpleCommandRunner
    ) -> None:
        """Test command execution with binary output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        # Simulate binary output with non-UTF8 bytes
        mock_process.communicate.return_value = (b"\xff\xfe\x00", b"")

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_process

            result = await runner.run_command(["binary_command"])

            assert result.success is True
            # Should handle binary data gracefully with replacement characters
            assert isinstance(result.stdout, str)
            assert isinstance(result.stderr, str)

    @pytest.mark.asyncio
    async def test_run_command_empty_output(self, runner: SimpleCommandRunner) -> None:
        """Test command execution with empty output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (None, None)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run_command(["true"])

            assert result.success is True
            assert result.stdout == ""
            assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_run_command_logging(self) -> None:
        """Test that command execution produces appropriate log messages."""
        # Create runner with logging enabled
        config = CommandRunnerConfig(timeout=30, log_commands=True)
        runner = SimpleCommandRunner(config=config)

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"output", b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process), patch(
            "borgitory.services.simple_command_runner.logger"
        ) as mock_logger:
            result = await runner.run_command(["echo", "test", "command"])

            assert result.success is True

            # Verify logging calls
            mock_logger.info.assert_any_call("Executing command: echo test command...")
            # Should log completion with duration and return code
            completion_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Command completed" in str(call)
            ]
            assert len(completion_calls) > 0

    @pytest.mark.asyncio
    async def test_run_command_failure_logging(self) -> None:
        """Test that failed commands produce warning logs."""
        # Create runner with logging enabled
        config = CommandRunnerConfig(timeout=30, log_commands=True)
        runner = SimpleCommandRunner(config=config)

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"command failed with error")

        with patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock
        ) as mock_create, patch(
            "borgitory.services.simple_command_runner.logger"
        ) as mock_logger:
            mock_create.return_value = mock_process

            result = await runner.run_command(["false"])

            assert result.success is False

            # Verify warning is logged for failure
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Command failed" in str(call)
            ]
            assert len(warning_calls) > 0

    def test_command_result_namedtuple(self) -> None:
        """Test CommandResult NamedTuple functionality."""
        result = CommandResult(
            success=True,
            return_code=0,
            stdout="output",
            stderr="",
            duration=1.5,
            error=None,
        )

        # Test field access
        assert result.success is True
        assert result.return_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration == 1.5
        assert result.error is None

        # Test mutability (CommandResult is now a regular class)
        # This should work without raising an exception
        result.success = False
        assert result.success is False

    def test_command_result_with_error(self) -> None:
        """Test CommandResult with error information."""
        result = CommandResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="error occurred",
            duration=0.5,
            error="error occurred",
        )

        assert result.success is False
        assert result.return_code == 1
        assert result.error == "error occurred"
        assert result.stderr == "error occurred"
