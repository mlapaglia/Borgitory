"""
Simple command runner for executing borg commands without job management overhead.

This runner is designed for simple operations like repository initialization,
scanning, etc. that don't need complex job tracking, streaming, or queuing.
"""

import logging
import asyncio
from typing import List, Dict, Optional

from borgitory.utils.datetime_utils import now_utc
from borgitory.protocols.command_protocols import CommandResult
from borgitory.config.command_runner_config import CommandRunnerConfig

logger = logging.getLogger(__name__)


class SimpleCommandRunner:
    """Simple command runner that executes commands and returns results directly"""

    def __init__(self, config: CommandRunnerConfig) -> None:
        """
        Initialize the command runner with configuration.

        Args:
            config: Configuration for command execution behavior
        """
        self.config = config
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
        start_time = now_utc()
        actual_timeout = timeout or self.timeout

        if self.log_commands:
            logger.info(f"Executing command: {' '.join(command[:3])}...")

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Wait for completion with timeout
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(), timeout=actual_timeout
                )

                # Decode output
                stdout = (
                    stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
                )
                stderr = (
                    stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
                )

                duration = (now_utc() - start_time).total_seconds()
                success = process.returncode == 0

                if self.log_commands:
                    logger.info(
                        f"Command completed in {duration:.2f}s with return code {process.returncode}"
                    )

                if not success and self.log_commands:
                    logger.warning(f"Command failed: {stderr[:200]}...")

                return CommandResult(
                    success=success,
                    return_code=process.returncode
                    if process.returncode is not None
                    else -1,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    error=stderr if not success else None,
                )

            except asyncio.TimeoutError:
                # Kill the process
                process.kill()
                await process.wait()

                duration = (now_utc() - start_time).total_seconds()
                error_msg = f"Command timed out after {actual_timeout} seconds"

                if self.log_commands:
                    logger.error(error_msg)

                return CommandResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr=error_msg,
                    duration=duration,
                    error=error_msg,
                )

        except Exception as e:
            duration = (now_utc() - start_time).total_seconds()
            error_msg = f"Failed to execute command: {str(e)}"

            if self.log_commands:
                logger.error(error_msg)

            return CommandResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=error_msg,
                duration=duration,
                error=error_msg,
            )
