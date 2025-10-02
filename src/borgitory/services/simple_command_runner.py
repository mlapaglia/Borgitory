"""
Simple command runner for executing borg commands without job management overhead.

This runner is designed for simple operations like repository initialization,
scanning, etc. that don't need complex job tracking, streaming, or queuing.
"""

import logging
from typing import List, Dict, Optional

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.command_protocols import CommandResult
from borgitory.config.command_runner_config import CommandRunnerConfig

logger = logging.getLogger(__name__)


class SimpleCommandRunner:
    """Simple command runner that executes commands and returns results directly"""

    def __init__(
        self, config: CommandRunnerConfig, executor: CommandExecutorProtocol
    ) -> None:
        """
        Initialize the command runner with configuration.

        Args:
            config: Configuration for command execution behavior
            executor: Command executor for cross-platform execution
        """
        self.config = config
        self.executor = executor
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        self.log_commands = config.log_commands
        self.buffer_size = config.buffer_size

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """
        Execute a command and return the result.

        Args:
            command: List of command and arguments
            env: Environment variables
            timeout: Override default timeout for this command

        Returns:
            CommandResult with execution details
        """
        actual_timeout = float(timeout or self.timeout)

        if self.log_commands:
            logger.info(f"Executing command: {' '.join(command[:3])}...")

        try:
            executor_result = await self.executor.execute_command(
                command=command,
                env=env,
                timeout=actual_timeout,
            )

            if self.log_commands:
                logger.info(
                    f"Command completed in {executor_result.execution_time:.2f}s with return code {executor_result.return_code}"
                )

            if not executor_result.success and self.log_commands:
                logger.warning(f"Command failed: {executor_result.stderr[:200]}...")

            # Convert from new CommandResult format to old format for backward compatibility
            return CommandResult(
                success=executor_result.success,
                return_code=executor_result.return_code,
                stdout=executor_result.stdout,
                stderr=executor_result.stderr,
                duration=executor_result.execution_time,
                error=executor_result.error,
            )

        except Exception as e:
            error_msg = f"Failed to execute command: {str(e)}"

            if self.log_commands:
                logger.error(error_msg)

            return CommandResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=error_msg,
                duration=0.0,
                error=error_msg,
            )
