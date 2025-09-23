"""
Tests for hook execution service.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from typing import Dict, List, Optional

from borgitory.services.hooks.hook_config import HookConfig
from borgitory.services.hooks.hook_execution_service import (
    HookExecutionService,
    DefaultHookOutputHandler,
)
from borgitory.protocols.command_protocols import CommandResult


class MockCommandRunner:
    """Mock command runner for testing."""

    def __init__(self) -> None:
        self._run_command_mock = AsyncMock()

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Mock run_command method."""
        return await self._run_command_mock(command=command, env=env, timeout=timeout)


class TestHookExecutionService:
    """Test HookExecutionService functionality."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default output handler."""
        mock_runner = MockCommandRunner()
        service = HookExecutionService(command_runner=mock_runner)

        assert service.command_runner == mock_runner
        assert isinstance(service.output_handler, DefaultHookOutputHandler)

    def test_init_with_custom_handler(self) -> None:
        """Test initialization with custom output handler."""
        mock_runner = MockCommandRunner()
        mock_handler = Mock()
        service = HookExecutionService(
            command_runner=mock_runner, output_handler=mock_handler
        )

        assert service.command_runner == mock_runner
        assert service.output_handler == mock_handler

    @pytest.mark.asyncio
    async def test_execute_hooks_empty_list(self) -> None:
        """Test executing empty hooks list returns empty results."""
        mock_runner = MockCommandRunner()
        service = HookExecutionService(command_runner=mock_runner)

        summary = await service.execute_hooks([], "pre", "job-123")

        assert summary.results == []
        assert summary.all_successful is True
        assert summary.critical_failure is False
        mock_runner._run_command_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_single_successful_hook(self) -> None:
        """Test executing a single successful hook."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="Hello World", stderr="", duration=0.5
        )

        service = HookExecutionService(command_runner=mock_runner)
        hook = HookConfig(name="Test Hook", command="echo 'Hello World'")

        summary = await service.execute_hooks([hook], "pre", "job-123")

        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.hook_name == "Test Hook"
        assert result.success is True
        assert result.return_code == 0
        assert result.output == "Hello World"
        assert result.error == ""
        assert summary.all_successful is True
        assert summary.critical_failure is False

        # Verify command was called correctly
        mock_runner._run_command_mock.assert_called_once()
        call_args = mock_runner._run_command_mock.call_args
        assert call_args[1]["command"] == ["/bin/bash", "-c", "echo 'Hello World'"]
        assert call_args[1]["timeout"] == 300

    @pytest.mark.asyncio
    async def test_execute_hook_with_custom_shell(self) -> None:
        """Test executing hook with custom shell."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        service = HookExecutionService(command_runner=mock_runner)
        hook = HookConfig(
            name="Shell Hook", command="ls -la", shell="/bin/sh", timeout=60
        )

        await service.execute_hooks([hook], "post", "job-456")

        # Verify correct shell and timeout were used
        call_args = mock_runner._run_command_mock.call_args
        assert call_args[1]["command"] == ["/bin/sh", "-c", "ls -la"]
        assert call_args[1]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_execute_hook_with_environment_vars(self) -> None:
        """Test executing hook with environment variables."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="test_value", stderr="", duration=0.1
        )

        service = HookExecutionService(command_runner=mock_runner)
        hook = HookConfig(
            name="Env Hook",
            command="echo $TEST_VAR",
            environment_vars={"TEST_VAR": "test_value"},
        )

        await service.execute_hooks([hook], "pre", "job-789")

        # Verify environment variables were passed
        call_args = mock_runner._run_command_mock.call_args
        env = call_args[1]["env"]
        assert "TEST_VAR" in env
        assert env["TEST_VAR"] == "test_value"

    @pytest.mark.asyncio
    async def test_execute_hook_with_context(self) -> None:
        """Test executing hook with additional context variables."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        service = HookExecutionService(command_runner=mock_runner)
        hook = HookConfig(name="Context Hook", command="echo $BORGITORY_REPOSITORY_ID")

        # Execute with context (matching production usage)
        context = {
            "repository_id": "test-repo-id",
            "task_index": "2",
            "job_type": "scheduled",
        }
        await service.execute_hooks([hook], "pre", "job-123", context)

        # Verify context was added to environment
        call_args = mock_runner._run_command_mock.call_args
        env = call_args[1]["env"]
        assert env["BORGITORY_REPOSITORY_ID"] == "test-repo-id"
        assert env["BORGITORY_TASK_INDEX"] == "2"
        assert env["BORGITORY_JOB_TYPE"] == "scheduled"

    @pytest.mark.asyncio
    async def test_execute_failed_hook(self) -> None:
        """Test executing a failed hook."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="Command failed",
            duration=0.2,
        )

        service = HookExecutionService(command_runner=mock_runner)
        hook = HookConfig(name="Failing Hook", command="exit 1")

        summary = await service.execute_hooks([hook], "pre", "job-123")

        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.hook_name == "Failing Hook"
        assert result.success is False
        assert result.return_code == 1
        assert result.error == "Command failed"

    @pytest.mark.asyncio
    async def test_execute_multiple_hooks_continue_on_failure(self) -> None:
        """Test executing multiple hooks with continue_on_failure=True."""
        mock_runner = MockCommandRunner()

        # First hook fails, second succeeds
        mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=False, return_code=1, stdout="", stderr="Failed", duration=0.1
            ),
            CommandResult(
                success=True, return_code=0, stdout="Success", stderr="", duration=0.1
            ),
        ]

        service = HookExecutionService(command_runner=mock_runner)
        hooks = [
            HookConfig(name="Hook 1", command="exit 1", continue_on_failure=True),
            HookConfig(name="Hook 2", command="echo Success", continue_on_failure=True),
        ]

        summary = await service.execute_hooks(hooks, "pre", "job-123")

        assert len(summary.results) == 2
        assert summary.results[0].success is False
        assert summary.results[1].success is True
        assert mock_runner._run_command_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_multiple_hooks_stop_on_failure(self) -> None:
        """Test executing multiple hooks with continue_on_failure=False."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=False, return_code=1, stdout="", stderr="Failed", duration=0.1
        )

        service = HookExecutionService(command_runner=mock_runner)
        hooks = [
            HookConfig(name="Hook 1", command="exit 1", continue_on_failure=False),
            HookConfig(name="Hook 2", command="echo Success", continue_on_failure=True),
        ]

        summary = await service.execute_hooks(hooks, "pre", "job-123")

        # Should only execute first hook
        assert len(summary.results) == 1
        assert summary.results[0].success is False
        assert mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_hook_with_output_logging(self) -> None:
        """Test hook execution with output logging."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True,
            return_code=0,
            stdout="Standard output",
            stderr="Error output",
            duration=0.1,
        )

        mock_handler = Mock()
        service = HookExecutionService(
            command_runner=mock_runner, output_handler=mock_handler
        )

        hook = HookConfig(name="Logging Hook", command="echo test", log_output=True)

        await service.execute_hooks([hook], "pre", "job-123")

        # Verify output was logged
        assert mock_handler.log_hook_output.call_count == 2
        mock_handler.log_hook_output.assert_any_call(
            "Logging Hook", "Standard output", False
        )
        mock_handler.log_hook_output.assert_any_call(
            "Logging Hook", "Error output", True
        )

    @pytest.mark.asyncio
    async def test_execute_hook_without_output_logging(self) -> None:
        """Test hook execution without output logging."""
        mock_runner = MockCommandRunner()
        mock_runner._run_command_mock.return_value = CommandResult(
            success=True,
            return_code=0,
            stdout="Standard output",
            stderr="Error output",
            duration=0.1,
        )

        mock_handler = Mock()
        service = HookExecutionService(
            command_runner=mock_runner, output_handler=mock_handler
        )

        hook = HookConfig(name="Silent Hook", command="echo test", log_output=False)

        await service.execute_hooks([hook], "pre", "job-123")

        # Verify output was not logged
        mock_handler.log_hook_output.assert_not_called()


class TestDefaultHookOutputHandler:
    """Test DefaultHookOutputHandler functionality."""

    def test_log_hook_output_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging hook output as info."""
        handler = DefaultHookOutputHandler()

        with caplog.at_level("INFO"):
            handler.log_hook_output("Test Hook", "Test output", False)

        assert "Hook 'Test Hook' output: Test output" in caplog.text

    def test_log_hook_output_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging hook output as error."""
        handler = DefaultHookOutputHandler()

        with caplog.at_level("ERROR"):
            handler.log_hook_output("Test Hook", "Test error", True)

        assert "Hook 'Test Hook' error: Test error" in caplog.text
