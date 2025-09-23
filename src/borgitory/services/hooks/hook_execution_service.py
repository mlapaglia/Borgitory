"""
Hook execution service for running pre and post job commands.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Protocol, NamedTuple

from borgitory.services.hooks.hook_config import HookConfig
from borgitory.protocols.command_protocols import CommandRunnerProtocol

logger = logging.getLogger(__name__)


class HookExecutionSummary(NamedTuple):
    """Summary of hook execution results."""

    results: List["HookExecutionResult"]
    all_successful: bool
    critical_failure: bool
    failed_critical_hook_name: Optional[str]


class HookOutputHandler(Protocol):
    """Protocol for handling hook command output."""

    def log_hook_output(
        self, hook_name: str, output: str, is_error: bool = False
    ) -> None:
        """Log hook output."""
        ...


class DefaultHookOutputHandler:
    """Default implementation of hook output handler."""

    def log_hook_output(
        self, hook_name: str, output: str, is_error: bool = False
    ) -> None:
        """Log hook output using standard logger."""
        if is_error:
            logger.error(f"Hook '{hook_name}' error: {output}")
        else:
            logger.info(f"Hook '{hook_name}' output: {output}")


class HookExecutionResult:
    """Result of hook execution."""

    def __init__(
        self,
        hook_name: str,
        success: bool,
        return_code: Optional[int] = None,
        output: str = "",
        error: str = "",
        execution_time: float = 0.0,
    ) -> None:
        self.hook_name = hook_name
        self.success = success
        self.return_code = return_code
        self.output = output
        self.error = error
        self.execution_time = execution_time


class HookExecutionService:
    """Service for executing hook commands with proper dependency injection."""

    def __init__(
        self,
        command_runner: CommandRunnerProtocol,
        output_handler: Optional[HookOutputHandler] = None,
    ) -> None:
        """
        Initialize the hook execution service.

        Args:
            command_runner: Service for executing system commands
            output_handler: Handler for hook output (optional, uses default if None)
        """
        self.command_runner = command_runner
        self.output_handler = output_handler or DefaultHookOutputHandler()

    async def execute_hooks(
        self,
        hooks: List[HookConfig],
        hook_type: str,
        job_id: str,
        context: Optional[Dict[str, str]] = None,
        job_failed: bool = False,
    ) -> HookExecutionSummary:
        """
        Execute a list of hooks sequentially.

        Args:
            hooks: List of hook configurations to execute
            hook_type: Type of hooks being executed ("pre" or "post")
            job_id: ID of the job these hooks are associated with
            context: Additional context variables for hook execution
            job_failed: Whether the job has failed (used for post-hook filtering)

        Returns:
            Summary of hook execution results including critical failure info
        """
        if not hooks:
            logger.debug(f"No {hook_type}-job hooks to execute for job {job_id}")
            return HookExecutionSummary(
                results=[],
                all_successful=True,
                critical_failure=False,
                failed_critical_hook_name=None,
            )

        # Filter post-hooks based on job status and run_on_job_failure setting
        hooks_to_execute = hooks
        if hook_type == "post":
            hooks_to_execute = []
            skipped_hooks = []
            for hook in hooks:
                should_run = hook.run_on_job_failure or not job_failed
                if should_run:
                    hooks_to_execute.append(hook)
                else:
                    skipped_hooks.append(hook)
                    logger.info(
                        f"Skipping post-hook '{hook.name}' because job failed and "
                        f"run_on_job_failure=False"
                    )

            if skipped_hooks:
                logger.info(
                    f"Skipped {len(skipped_hooks)} post-hooks due to job failure, "
                    f"executing {len(hooks_to_execute)} hooks"
                )

        logger.info(
            f"Executing {len(hooks_to_execute)} {hook_type}-job hooks for job {job_id}"
        )
        results = []
        critical_failure = False
        failed_critical_hook_name = None

        for i, hook in enumerate(hooks_to_execute):
            logger.info(
                f"Executing {hook_type}-job hook {i + 1}/{len(hooks_to_execute)}: {hook.name} "
                f"(critical: {hook.critical})"
            )

            result = await self._execute_single_hook(hook, job_id, context)
            results.append(result)

            if not result.success:
                if hook.critical:
                    critical_failure = True
                    failed_critical_hook_name = hook.name
                    logger.error(
                        f"Critical hook '{hook.name}' failed, stopping execution of "
                        f"remaining {hook_type}-job hooks and failing entire job"
                    )
                    break
                elif not hook.continue_on_failure:
                    logger.error(
                        f"Hook '{hook.name}' failed and continue_on_failure=False, "
                        f"stopping execution of remaining {hook_type}-job hooks"
                    )
                    break
                else:
                    logger.warning(
                        f"Hook '{hook.name}' failed but continue_on_failure=True, "
                        f"continuing with remaining hooks"
                    )

        successful_hooks = sum(1 for r in results if r.success)
        all_successful = all(r.success for r in results)

        logger.info(
            f"Completed {hook_type}-job hooks for job {job_id}: "
            f"{successful_hooks}/{len(results)} successful"
            f"{' (CRITICAL FAILURE)' if critical_failure else ''}"
        )

        return HookExecutionSummary(
            results=results,
            all_successful=all_successful,
            critical_failure=critical_failure,
            failed_critical_hook_name=failed_critical_hook_name,
        )

    async def _execute_single_hook(
        self, hook: HookConfig, job_id: str, context: Optional[Dict[str, str]] = None
    ) -> HookExecutionResult:
        """
        Execute a single hook command.

        Args:
            hook: Hook configuration to execute
            job_id: ID of the associated job
            context: Additional context variables

        Returns:
            Execution result for the hook
        """
        import time

        start_time = time.time()

        try:
            # Prepare environment variables
            env = os.environ.copy()
            env.update(hook.environment_vars)

            # Add job context to environment
            if context:
                for key, value in context.items():
                    env[f"BORGITORY_{key.upper()}"] = value

            # Prepare command
            command = [hook.shell, "-c", hook.command]

            logger.debug(f"Executing hook '{hook.name}' with command: {command}")

            # Execute with timeout
            try:
                result = await asyncio.wait_for(
                    self.command_runner.run_command(
                        command=command, env=env, timeout=hook.timeout
                    ),
                    timeout=hook.timeout + 5,  # Add small buffer for cleanup
                )

                execution_time = time.time() - start_time
                success = result.success
                return_code = result.return_code
                stdout = result.stdout
                stderr = result.stderr

                # Log output if requested
                if hook.log_output:
                    if stdout:
                        self.output_handler.log_hook_output(hook.name, stdout, False)
                    if stderr:
                        self.output_handler.log_hook_output(hook.name, stderr, True)

                if success:
                    logger.info(
                        f"Hook '{hook.name}' completed successfully in {execution_time:.2f}s"
                    )
                else:
                    logger.warning(
                        f"Hook '{hook.name}' failed with return code {return_code} "
                        f"in {execution_time:.2f}s"
                    )

                return HookExecutionResult(
                    hook_name=hook.name,
                    success=success,
                    return_code=return_code,
                    output=stdout,
                    error=stderr,
                    execution_time=execution_time,
                )

            except asyncio.TimeoutError:
                execution_time = time.time() - start_time
                error_msg = f"Hook '{hook.name}' timed out after {hook.timeout}s"
                logger.error(error_msg)

                return HookExecutionResult(
                    hook_name=hook.name,
                    success=False,
                    return_code=None,
                    output="",
                    error=error_msg,
                    execution_time=execution_time,
                )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Hook '{hook.name}' execution failed: {str(e)}"
            logger.error(error_msg)

            return HookExecutionResult(
                hook_name=hook.name,
                success=False,
                return_code=None,
                output="",
                error=error_msg,
                execution_time=execution_time,
            )
