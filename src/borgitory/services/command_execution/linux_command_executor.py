"""
Linux Command Executor for Linux and Docker environments.

This executor handles direct command execution on Linux-like systems,
including native Linux and Docker containers.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

from borgitory.protocols.command_executor_protocol import (
    CommandExecutorProtocol,
    CommandResult,
)

logger = logging.getLogger(__name__)


class LinuxCommandExecutor(CommandExecutorProtocol):
    """Command executor for Linux-like environments (Linux, Docker)."""

    def __init__(self, default_timeout: float = 300.0) -> None:
        """
        Initialize Linux command executor.

        Args:
            default_timeout: Default timeout for commands in seconds
        """
        self.default_timeout = default_timeout

    async def execute_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        input_data: Optional[str] = None,
    ) -> CommandResult:
        """Execute a command and return the result."""
        start_time = time.time()
        actual_timeout = timeout or self.default_timeout

        logger.debug(
            f"Executing Linux command: {' '.join(command[:3])}... (timeout: {actual_timeout}s)"
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                env=env,
                cwd=cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input_data.encode() if input_data else None),
                    timeout=actual_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                execution_time = time.time() - start_time
                return CommandResult(
                    command=command,
                    return_code=-1,
                    stdout="",
                    stderr="",
                    success=False,
                    execution_time=execution_time,
                    error=f"Command timed out after {actual_timeout} seconds",
                )

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            execution_time = time.time() - start_time
            success = process.returncode == 0

            result = CommandResult(
                command=command,
                return_code=process.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
                success=success,
                execution_time=execution_time,
                error=stderr_str if not success and stderr_str else None,
            )

            if success:
                logger.debug(
                    f"Linux command completed successfully in {execution_time:.2f}s"
                )
            else:
                logger.warning(
                    f"Linux command failed (code {result.return_code}) in {execution_time:.2f}s: {stderr_str}"
                )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Linux command execution failed: {str(e)}"
            logger.error(f"{error_msg} (Command: {' '.join(command)})")
            logger.exception("Full exception details:")

            return CommandResult(
                command=command,
                return_code=-1,
                stdout="",
                stderr="",
                success=False,
                execution_time=execution_time,
                error=error_msg,
            )

    async def create_subprocess(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdout: Optional[int] = None,
        stderr: Optional[int] = None,
        stdin: Optional[int] = None,
    ) -> asyncio.subprocess.Process:
        """Create a subprocess for streaming operations."""
        logger.debug(f"Creating Linux subprocess: {' '.join(command[:3])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=stdout or asyncio.subprocess.PIPE,
                stderr=stderr or asyncio.subprocess.PIPE,
                stdin=stdin,
                env=env,
                cwd=cwd,
            )

            logger.debug(f"Linux subprocess created successfully (PID: {process.pid})")
            return process

        except Exception as e:
            logger.error(f"Failed to create Linux subprocess: {e}")
            raise

    def get_platform_name(self) -> str:
        """Get the platform name this executor handles."""
        return "linux"
