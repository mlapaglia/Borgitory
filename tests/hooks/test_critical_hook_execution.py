"""
Tests for HookExecutionService critical failure and early exit logic.
"""

import pytest
from typing import Dict, List, Optional, Any
from unittest.mock import AsyncMock

from src.borgitory.services.hooks.hook_config import HookConfig
from src.borgitory.services.hooks.hook_execution_service import HookExecutionService
from src.borgitory.protocols.command_protocols import CommandResult


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


class MockOutputHandler:
    """Mock output handler for testing."""

    def __init__(self) -> None:
        self.logged_outputs: List[Dict[str, Any]] = []

    def log_hook_output(
        self, hook_name: str, output: str, is_error: bool = False
    ) -> None:
        """Mock log_hook_output method."""
        self.logged_outputs.append(
            {"hook_name": hook_name, "output": output, "is_error": is_error}
        )


class TestHookExecutionServiceCriticalFailure:
    """Test HookExecutionService critical failure handling."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        self.mock_runner = MockCommandRunner()
        self.mock_output_handler = MockOutputHandler()
        self.service = HookExecutionService(
            command_runner=self.mock_runner, output_handler=self.mock_output_handler
        )

    @pytest.mark.asyncio
    async def test_critical_hook_failure_stops_execution(self) -> None:
        """Test that critical hook failure stops remaining hook execution."""
        # Setup hooks - first critical, second non-critical
        hooks = [
            HookConfig(name="critical hook", command="fail", critical=True),
            HookConfig(name="normal hook", command="success", critical=False),
        ]

        # Mock first command to fail, second should not be called
        self.mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="Command failed",
                duration=0.1,
            ),
            CommandResult(
                success=True, return_code=0, stdout="success", stderr="", duration=0.1
            ),
        ]

        # Execute hooks
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="pre", job_id="test-job-123"
        )

        # Verify critical failure detected
        assert summary.critical_failure is True
        assert summary.failed_critical_hook_name == "critical hook"
        assert summary.all_successful is False
        assert len(summary.results) == 1  # Only first hook executed

        # Verify first hook failed
        assert summary.results[0].hook_name == "critical hook"
        assert summary.results[0].success is False

        # Verify only first command was called
        assert self.mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_non_critical_hook_failure_continues_execution(self) -> None:
        """Test that non-critical hook failure allows remaining hooks to execute."""
        # Setup hooks - first non-critical, second non-critical
        hooks = [
            HookConfig(name="non-critical hook", command="fail", critical=False),
            HookConfig(name="normal hook", command="success", critical=False),
        ]

        # Mock first command to fail, second to succeed
        self.mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="Command failed",
                duration=0.1,
            ),
            CommandResult(
                success=True, return_code=0, stdout="success", stderr="", duration=0.1
            ),
        ]

        # Execute hooks
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="pre", job_id="test-job-123"
        )

        # Verify no critical failure
        assert summary.critical_failure is False
        assert summary.failed_critical_hook_name is None
        assert summary.all_successful is False  # One failed, but not critical
        assert len(summary.results) == 2  # Both hooks executed

        # Verify both commands were called
        assert self.mock_runner._run_command_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_critical_hook_success_continues_execution(self) -> None:
        """Test that critical hook success allows remaining hooks to execute."""
        # Setup hooks - first critical (succeeds), second normal
        hooks = [
            HookConfig(name="critical hook", command="success", critical=True),
            HookConfig(name="normal hook", command="success", critical=False),
        ]

        # Mock both commands to succeed
        self.mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=True, return_code=0, stdout="success1", stderr="", duration=0.1
            ),
            CommandResult(
                success=True, return_code=0, stdout="success2", stderr="", duration=0.1
            ),
        ]

        # Execute hooks
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="pre", job_id="test-job-123"
        )

        # Verify no critical failure
        assert summary.critical_failure is False
        assert summary.failed_critical_hook_name is None
        assert summary.all_successful is True
        assert len(summary.results) == 2  # Both hooks executed

        # Verify both hooks succeeded
        assert all(result.success for result in summary.results)

        # Verify both commands were called
        assert self.mock_runner._run_command_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_critical_hooks_first_fails(self) -> None:
        """Test multiple critical hooks where first one fails."""
        # Setup hooks - both critical
        hooks = [
            HookConfig(name="critical hook 1", command="fail", critical=True),
            HookConfig(name="critical hook 2", command="success", critical=True),
        ]

        # Mock first command to fail
        self.mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="Command failed",
                duration=0.1,
            )
        ]

        # Execute hooks
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="pre", job_id="test-job-123"
        )

        # Verify critical failure on first hook
        assert summary.critical_failure is True
        assert summary.failed_critical_hook_name == "critical hook 1"
        assert len(summary.results) == 1  # Only first hook executed

        # Verify only first command was called
        assert self.mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_continue_on_failure_with_non_critical_hook(self) -> None:
        """Test continue_on_failure=False with non-critical hook stops execution."""
        # Setup hooks - first non-critical with continue_on_failure=False
        hooks = [
            HookConfig(
                name="non-critical strict",
                command="fail",
                critical=False,
                continue_on_failure=False,
            ),
            HookConfig(name="normal hook", command="success", critical=False),
        ]

        # Mock first command to fail
        self.mock_runner._run_command_mock.side_effect = [
            CommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="Command failed",
                duration=0.1,
            )
        ]

        # Execute hooks
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="pre", job_id="test-job-123"
        )

        # Verify no critical failure (since hook wasn't critical)
        assert summary.critical_failure is False
        assert summary.failed_critical_hook_name is None
        assert summary.all_successful is False
        assert len(summary.results) == 1  # Only first hook executed

        # Verify only first command was called
        assert self.mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_hooks_list(self) -> None:
        """Test executing empty hooks list returns successful summary."""
        summary = await self.service.execute_hooks(
            hooks=[], hook_type="pre", job_id="test-job-123"
        )

        assert summary.critical_failure is False
        assert summary.failed_critical_hook_name is None
        assert summary.all_successful is True
        assert len(summary.results) == 0

        # Verify no commands were called
        assert self.mock_runner._run_command_mock.call_count == 0


class TestHookExecutionServicePostHookConditional:
    """Test HookExecutionService post-hook conditional execution."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        self.mock_runner = MockCommandRunner()
        self.service = HookExecutionService(command_runner=self.mock_runner)

    @pytest.mark.asyncio
    async def test_post_hook_runs_on_job_success(self) -> None:
        """Test post-hook runs when job succeeded and run_on_job_failure=False."""
        hooks = [
            HookConfig(
                name="success only hook", command="success", run_on_job_failure=False
            )
        ]

        # Mock command to succeed
        self.mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="success", stderr="", duration=0.1
        )

        # Execute hooks with job_failed=False (job succeeded)
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="post", job_id="test-job-123", job_failed=False
        )

        assert len(summary.results) == 1
        assert summary.results[0].hook_name == "success only hook"
        assert self.mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_post_hook_skipped_on_job_failure(self) -> None:
        """Test post-hook skipped when job failed and run_on_job_failure=False."""
        hooks = [
            HookConfig(
                name="success only hook", command="success", run_on_job_failure=False
            )
        ]

        # Execute hooks with job_failed=True (job failed)
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="post", job_id="test-job-123", job_failed=True
        )

        # Hook should be skipped
        assert len(summary.results) == 0
        assert summary.all_successful is True  # No hooks ran, so "successful"
        assert self.mock_runner._run_command_mock.call_count == 0

    @pytest.mark.asyncio
    async def test_post_hook_runs_on_job_failure_when_configured(self) -> None:
        """Test post-hook runs when job failed and run_on_job_failure=True."""
        hooks = [
            HookConfig(
                name="failure cleanup hook", command="cleanup", run_on_job_failure=True
            )
        ]

        # Mock command to succeed
        self.mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="cleanup done", stderr="", duration=0.1
        )

        # Execute hooks with job_failed=True (job failed)
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="post", job_id="test-job-123", job_failed=True
        )

        assert len(summary.results) == 1
        assert summary.results[0].hook_name == "failure cleanup hook"
        assert self.mock_runner._run_command_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_mixed_post_hooks_on_job_failure(self) -> None:
        """Test mixed post-hooks where some run on failure, others don't."""
        hooks = [
            HookConfig(
                name="success only hook", command="success", run_on_job_failure=False
            ),
            HookConfig(
                name="failure cleanup hook", command="cleanup", run_on_job_failure=True
            ),
            HookConfig(
                name="always run hook", command="always", run_on_job_failure=True
            ),
        ]

        # Mock commands to succeed
        self.mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="success", stderr="", duration=0.1
        )

        # Execute hooks with job_failed=True (job failed)
        summary = await self.service.execute_hooks(
            hooks=hooks, hook_type="post", job_id="test-job-123", job_failed=True
        )

        # Only hooks with run_on_job_failure=True should execute
        assert len(summary.results) == 2
        executed_names = [result.hook_name for result in summary.results]
        assert "failure cleanup hook" in executed_names
        assert "always run hook" in executed_names
        assert "success only hook" not in executed_names

        assert self.mock_runner._run_command_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_pre_hooks_ignore_job_failed_parameter(self) -> None:
        """Test pre-hooks always execute regardless of job_failed parameter."""
        hooks = [HookConfig(name="pre hook", command="pre", run_on_job_failure=False)]

        # Mock command to succeed
        self.mock_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout="success", stderr="", duration=0.1
        )

        # Execute pre-hooks with job_failed=True (shouldn't matter for pre-hooks)
        summary = await self.service.execute_hooks(
            hooks=hooks,
            hook_type="pre",  # Pre-hooks
            job_id="test-job-123",
            job_failed=True,
        )

        # Pre-hook should still execute
        assert len(summary.results) == 1
        assert summary.results[0].hook_name == "pre hook"
        assert self.mock_runner._run_command_mock.call_count == 1
