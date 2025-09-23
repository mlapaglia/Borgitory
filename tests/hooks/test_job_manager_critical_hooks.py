"""
Tests for JobManager hook task execution with critical failures.
"""

import pytest
from typing import Dict, List, Optional
from unittest.mock import AsyncMock

from src.borgitory.services.jobs.job_manager import (
    JobManager,
    BorgJob,
    BorgJobTask,
    JobManagerDependencies,
)
from src.borgitory.services.hooks.hook_execution_service import (
    HookExecutionSummary,
    HookExecutionResult,
)
from src.borgitory.services.hooks.hook_config import HookConfig
from src.borgitory.utils.datetime_utils import now_utc


class MockHookExecutionService:
    """Mock HookExecutionService for testing."""

    def __init__(self) -> None:
        self.execute_hooks_mock = AsyncMock()

    async def execute_hooks(
        self,
        hooks: List[HookConfig],
        hook_type: str,
        job_id: str,
        context: Optional[Dict[str, str]] = None,
        job_failed: bool = False,
    ) -> HookExecutionSummary:
        """Mock execute_hooks method."""
        return await self.execute_hooks_mock(
            hooks=hooks,
            hook_type=hook_type,
            job_id=job_id,
            context=context,
            job_failed=job_failed,
        )


class TestJobManagerHookExecution:
    """Test JobManager hook task execution logic."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        self.mock_hook_service = MockHookExecutionService()

        # Create minimal dependencies for JobManager
        self.dependencies = JobManagerDependencies(
            hook_execution_service=self.mock_hook_service
        )

        self.job_manager = JobManager(dependencies=self.dependencies)

    def create_test_job(self, tasks: List[BorgJobTask]) -> BorgJob:
        """Helper to create test job with tasks."""
        return BorgJob(
            id="test-job-123",
            job_type="composite",
            repository_id=1,
            status="running",
            started_at=now_utc(),
            tasks=tasks,
        )

    def create_hook_task(
        self, hook_type: str, hooks_json: str, task_name: Optional[str] = None
    ) -> BorgJobTask:
        """Helper to create hook task."""
        return BorgJobTask(
            task_type="hook",
            task_name=task_name or f"{hook_type}-job hooks",
            parameters={"hook_type": hook_type, "hooks": hooks_json},
        )

    @pytest.mark.asyncio
    async def test_execute_hook_task_success(self) -> None:
        """Test successful hook task execution."""
        # Setup successful hook execution
        self.mock_hook_service.execute_hooks_mock.return_value = HookExecutionSummary(
            results=[
                HookExecutionResult(
                    hook_name="test hook",
                    success=True,
                    return_code=0,
                    output="success output",
                    error="",
                    execution_time=0.1,
                )
            ],
            all_successful=True,
            critical_failure=False,
            failed_critical_hook_name=None,
        )

        # Create test job and task
        hooks_json = (
            '[{"name": "test hook", "command": "echo test", "critical": false}]'
        )
        hook_task = self.create_hook_task("pre", hooks_json)
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify success
        assert result is True
        assert hook_task.status == "completed"
        assert hook_task.return_code == 0
        assert hook_task.error is None
        assert len(hook_task.output_lines) == 1
        assert "test hook" in hook_task.output_lines[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_hook_task_critical_failure(self) -> None:
        """Test hook task execution with critical failure."""
        # Setup critical hook failure
        self.mock_hook_service.execute_hooks_mock.return_value = HookExecutionSummary(
            results=[
                HookExecutionResult(
                    hook_name="critical hook",
                    success=False,
                    return_code=1,
                    output="",
                    error="Critical command failed",
                    execution_time=0.1,
                )
            ],
            all_successful=False,
            critical_failure=True,
            failed_critical_hook_name="critical hook",
        )

        # Create test job and task
        hooks_json = '[{"name": "critical hook", "command": "fail", "critical": true}]'
        hook_task = self.create_hook_task("pre", hooks_json)
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify failure
        assert result is False
        assert hook_task.status == "failed"
        assert hook_task.return_code == 1
        assert "Critical hook execution failed" in hook_task.error

        # Verify critical failure parameters are set
        assert hook_task.parameters["critical_failure"] is True
        assert hook_task.parameters["failed_critical_hook_name"] == "critical hook"

    @pytest.mark.asyncio
    async def test_execute_hook_task_non_critical_failure(self) -> None:
        """Test hook task execution with non-critical failure."""
        # Setup non-critical hook failure
        self.mock_hook_service.execute_hooks_mock.return_value = HookExecutionSummary(
            results=[
                HookExecutionResult(
                    hook_name="normal hook",
                    success=False,
                    return_code=1,
                    output="",
                    error="Command failed",
                    execution_time=0.1,
                )
            ],
            all_successful=False,
            critical_failure=False,
            failed_critical_hook_name=None,
        )

        # Create test job and task
        hooks_json = '[{"name": "normal hook", "command": "fail", "critical": false}]'
        hook_task = self.create_hook_task("pre", hooks_json)
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify failure but not critical
        assert result is False
        assert hook_task.status == "failed"
        assert hook_task.return_code == 1
        assert "Hook execution failed" in hook_task.error
        assert "Critical" not in hook_task.error

        # Verify critical failure parameters are NOT set
        assert hook_task.parameters.get("critical_failure") is None
        assert hook_task.parameters.get("failed_critical_hook_name") is None

    @pytest.mark.asyncio
    async def test_execute_hook_task_post_hook_with_job_failure(self) -> None:
        """Test post-hook execution with job failure status."""
        # Setup successful post-hook execution
        self.mock_hook_service.execute_hooks_mock.return_value = HookExecutionSummary(
            results=[
                HookExecutionResult(
                    hook_name="cleanup hook",
                    success=True,
                    return_code=0,
                    output="cleanup done",
                    error="",
                    execution_time=0.1,
                )
            ],
            all_successful=True,
            critical_failure=False,
            failed_critical_hook_name=None,
        )

        # Create test job and task
        hooks_json = '[{"name": "cleanup hook", "command": "cleanup", "run_on_job_failure": true}]'
        hook_task = self.create_hook_task("post", hooks_json)
        job = self.create_test_job([hook_task])

        # Execute hook task with job_has_failed=True
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, True)

        # Verify success
        assert result is True
        assert hook_task.status == "completed"

        # Verify hook service was called with job_failed=True
        self.mock_hook_service.execute_hooks_mock.assert_called_once()
        call_args = self.mock_hook_service.execute_hooks_mock.call_args
        assert call_args.kwargs["job_failed"] is True

    @pytest.mark.asyncio
    async def test_execute_hook_task_no_hooks_json(self) -> None:
        """Test hook task execution with empty hooks JSON."""
        # Create test job and task with empty hooks
        hook_task = self.create_hook_task("pre", "")
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify success (no hooks to execute)
        assert result is True
        assert hook_task.status == "completed"
        assert hook_task.return_code == 0

        # Verify hook service was not called
        self.mock_hook_service.execute_hooks_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_hook_task_invalid_json(self) -> None:
        """Test hook task execution with invalid JSON."""
        # Create test job and task with invalid JSON
        hook_task = self.create_hook_task("pre", "invalid json")
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await self.job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify failure due to invalid JSON
        assert result is False
        assert hook_task.status == "failed"
        assert hook_task.return_code == 1
        assert "Invalid hook configuration" in hook_task.error

        # Verify hook service was not called
        self.mock_hook_service.execute_hooks_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_hook_task_no_hook_service(self) -> None:
        """Test hook task execution when hook service is not available."""
        # Create JobManager without hook service
        dependencies = JobManagerDependencies(hook_execution_service=None)
        job_manager = JobManager(dependencies=dependencies)

        # Create test job and task
        hooks_json = '[{"name": "test hook", "command": "echo test"}]'
        hook_task = self.create_hook_task("pre", hooks_json)
        job = self.create_test_job([hook_task])

        # Execute hook task
        result = await job_manager._execute_hook_task(job, hook_task, 0, False)

        # Verify failure due to missing service
        assert result is False
        assert hook_task.status == "failed"
        assert "Hook execution service not configured" in hook_task.error

    @pytest.mark.asyncio
    async def test_execute_hook_task_context_parameters(self) -> None:
        """Test hook task execution passes correct context parameters."""
        # Setup successful hook execution
        self.mock_hook_service.execute_hooks_mock.return_value = HookExecutionSummary(
            results=[],
            all_successful=True,
            critical_failure=False,
            failed_critical_hook_name=None,
        )

        # Create test job and task
        hooks_json = '[{"name": "test hook", "command": "echo test"}]'
        hook_task = self.create_hook_task("pre", hooks_json)
        job = self.create_test_job([hook_task])
        job.repository_id = 42
        job.job_type = "scheduled"

        # Execute hook task
        await self.job_manager._execute_hook_task(job, hook_task, 3, False)

        # Verify context parameters were passed correctly
        self.mock_hook_service.execute_hooks_mock.assert_called_once()
        call_args = self.mock_hook_service.execute_hooks_mock.call_args

        assert call_args.kwargs["hook_type"] == "pre"
        assert call_args.kwargs["job_id"] == "test-job-123"
        assert call_args.kwargs["job_failed"] is False

        context = call_args.kwargs["context"]
        assert context["repository_id"] == "42"
        assert context["task_index"] == "3"
        assert context["job_type"] == "scheduled"
