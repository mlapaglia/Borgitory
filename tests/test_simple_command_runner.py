"""
Tests for SimpleCommandRunner service - Updated for Command Executor Pattern
"""

import pytest
from unittest.mock import Mock, AsyncMock

from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.protocols.command_protocols import CommandResult
from borgitory.protocols.command_executor_protocol import (
    CommandExecutorProtocol,
    CommandResult as ExecutorCommandResult,
)
from borgitory.config.command_runner_config import CommandRunnerConfig


class TestSimpleCommandRunner:
    """Test class for SimpleCommandRunner."""

    @pytest.fixture
    def test_config(self) -> CommandRunnerConfig:
        """Create test configuration."""
        return CommandRunnerConfig(timeout=30, max_retries=1, log_commands=False)

    @pytest.fixture
    def mock_executor(self) -> Mock:
        """Create mock command executor."""
        mock = Mock(spec=CommandExecutorProtocol)
        mock.execute_command = AsyncMock()
        return mock

    @pytest.fixture
    def runner(
        self, test_config: CommandRunnerConfig, mock_executor: Mock
    ) -> SimpleCommandRunner:
        """Create SimpleCommandRunner instance for testing."""
        return SimpleCommandRunner(config=test_config, executor=mock_executor)

    def test_initialization(self) -> None:
        """Test SimpleCommandRunner initialization."""
        default_config = CommandRunnerConfig()
        mock_executor = Mock(spec=CommandExecutorProtocol)
        runner = SimpleCommandRunner(config=default_config, executor=mock_executor)
        assert runner.timeout == 300  # Default timeout
        assert runner.max_retries == 3
        assert runner.log_commands is True

        custom_config = CommandRunnerConfig(
            timeout=60, max_retries=5, log_commands=False
        )
        runner_custom = SimpleCommandRunner(
            config=custom_config, executor=mock_executor
        )
        assert runner_custom.timeout == 60
        assert runner_custom.max_retries == 5
        assert runner_custom.log_commands is False

    async def test_run_command_success(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test successful command execution."""
        # Mock the executor to return a successful result
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["echo", "test"],
            return_code=0,
            stdout="output",
            stderr="",
            success=True,
            execution_time=1.5,
        )

        result = await runner.run_command(["echo", "test"])

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.return_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration == 1.5
        assert result.error is None
        mock_executor.execute_command.assert_called_once()

    async def test_run_command_failure(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test failed command execution."""
        # Mock the executor to return a failed result
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["false"],
            return_code=1,
            stdout="",
            stderr="error message",
            success=False,
            execution_time=2.0,
            error="error message",
        )

        result = await runner.run_command(["false"])

        assert isinstance(result, CommandResult)
        assert result.success is False
        assert result.return_code == 1
        assert result.stdout == ""
        assert result.stderr == "error message"
        assert result.duration == 2.0
        assert result.error == "error message"

    async def test_run_command_timeout(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution timeout."""
        # Mock the executor to return a timeout result
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["sleep", "60"],
            return_code=-1,
            stdout="",
            stderr="Command timed out after 30.0 seconds",
            success=False,
            execution_time=30.0,
            error="Command timed out after 30.0 seconds",
        )

        result = await runner.run_command(["sleep", "60"])

        assert isinstance(result, CommandResult)
        assert result.success is False
        assert result.return_code == -1
        assert result.duration == 30.0
        assert result.error is not None
        assert "timed out" in result.error

    async def test_run_command_with_env(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution with environment variables."""
        env_vars = {"TEST_VAR": "test_value"}

        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["env"],
            return_code=0,
            stdout="TEST_VAR=test_value\n",
            stderr="",
            success=True,
            execution_time=1.0,
        )

        result = await runner.run_command(["env"], env=env_vars)

        assert result.success is True
        assert "TEST_VAR=test_value" in result.stdout

        # Verify the executor was called with the environment variables
        mock_executor.execute_command.assert_called_once()
        call_args = mock_executor.execute_command.call_args
        assert call_args[1]["env"] == env_vars

    async def test_run_command_custom_timeout(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution with custom timeout."""
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["echo", "test"],
            return_code=0,
            stdout="test",
            stderr="",
            success=True,
            execution_time=1.0,
        )

        result = await runner.run_command(["echo", "test"], timeout=60)

        assert result.success is True

        # Verify the executor was called with the custom timeout
        mock_executor.execute_command.assert_called_once()
        call_args = mock_executor.execute_command.call_args
        assert call_args[1]["timeout"] == 60.0

    async def test_run_command_exception_handling(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution when executor raises an exception."""
        mock_executor.execute_command.side_effect = Exception("Executor failed")

        result = await runner.run_command(["echo", "test"])

        assert isinstance(result, CommandResult)
        assert result.success is False
        assert result.return_code == -1
        assert result.error is not None
        assert "Failed to execute command" in result.error
        assert "Executor failed" in result.error

    async def test_run_command_with_binary_output(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution with binary output."""
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["cat", "binary_file"],
            return_code=0,
            stdout="binary\x00data\xff",
            stderr="",
            success=True,
            execution_time=1.0,
        )

        result = await runner.run_command(["cat", "binary_file"])

        assert result.success is True
        assert result.stdout == "binary\x00data\xff"

    async def test_run_command_empty_output(
        self, runner: SimpleCommandRunner, mock_executor: Mock
    ) -> None:
        """Test command execution with empty output."""
        mock_executor.execute_command.return_value = ExecutorCommandResult(
            command=["true"],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            execution_time=0.1,
        )

        result = await runner.run_command(["true"])

        assert result.success is True
        assert result.stdout == ""
        assert result.stderr == ""

    async def test_run_command_logging_enabled(self) -> None:
        """Test command execution with logging enabled."""
        config = CommandRunnerConfig(log_commands=True)
        mock_executor = Mock(spec=CommandExecutorProtocol)
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["echo", "test"],
                return_code=0,
                stdout="test",
                stderr="",
                success=True,
                execution_time=1.0,
            )
        )

        runner = SimpleCommandRunner(config=config, executor=mock_executor)

        # This test mainly ensures no exceptions are raised when logging is enabled
        result = await runner.run_command(["echo", "test"])
        assert result.success is True

    async def test_run_command_failure_logging(self) -> None:
        """Test command execution failure with logging enabled."""
        config = CommandRunnerConfig(log_commands=True)
        mock_executor = Mock(spec=CommandExecutorProtocol)
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["false"],
                return_code=1,
                stdout="",
                stderr="command failed",
                success=False,
                execution_time=1.0,
                error="command failed",
            )
        )

        runner = SimpleCommandRunner(config=config, executor=mock_executor)

        # This test mainly ensures no exceptions are raised when logging failures
        result = await runner.run_command(["false"])
        assert result.success is False
        assert result.error == "command failed"
