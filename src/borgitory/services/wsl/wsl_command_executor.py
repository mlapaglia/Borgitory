"""
WSL Command Executor for running commands through Windows Subsystem for Linux.

This service provides a wrapper around subprocess execution that routes
all commands through WSL, enabling Unix-style command execution on Windows.
"""

import asyncio
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WSLCommandResult:
    """Result of a WSL command execution."""

    command: List[str]
    return_code: int
    stdout: str
    stderr: str
    success: bool
    execution_time: float
    error: Optional[str] = None


class WSLCommandExecutor:
    """Executor for running commands through WSL."""

    def __init__(self, distribution: Optional[str] = None, timeout: float = 300.0):
        """
        Initialize WSL command executor.

        Args:
            distribution: Specific WSL distribution to use (None for default)
            timeout: Default timeout for commands in seconds
        """
        self.distribution = distribution
        self.default_timeout = timeout

    async def execute_command(
        self,
        command: Union[str, List[str]],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        input_data: Optional[str] = None,
    ) -> WSLCommandResult:
        """
        Execute a command through WSL.

        Args:
            command: Command to execute (string or list)
            env: Environment variables to set
            cwd: Working directory (WSL path)
            timeout: Command timeout in seconds
            input_data: Data to send to command stdin

        Returns:
            WSLCommandResult with execution details
        """
        start_time = time.time()

        # Convert command to list if it's a string
        if isinstance(command, str):
            cmd_list = command.split()
        else:
            cmd_list = list(command)

        # Build WSL command
        wsl_command = self._build_wsl_command(cmd_list, env, cwd)

        actual_timeout = timeout or self.default_timeout

        logger.debug(
            f"Executing WSL command: {' '.join(wsl_command[:3])}... (timeout: {actual_timeout}s)"
        )

        try:
            # Use ThreadPoolExecutor to run synchronous subprocess in async context
            # This avoids the NotImplementedError on Windows with asyncio.create_subprocess_exec
            loop = asyncio.get_event_loop()

            def run_subprocess() -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(
                    wsl_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE if input_data else None,
                    input=input_data.encode() if input_data else None,
                    timeout=actual_timeout,
                    text=False,  # Keep as bytes for consistent decoding
                )

            # Execute in thread pool to avoid blocking the event loop
            with ThreadPoolExecutor() as executor:
                try:
                    process_result = await loop.run_in_executor(
                        executor, run_subprocess
                    )
                except subprocess.TimeoutExpired:
                    execution_time = time.time() - start_time
                    return WSLCommandResult(
                        command=cmd_list,
                        return_code=-1,
                        stdout="",
                        stderr="",
                        success=False,
                        execution_time=execution_time,
                        error=f"Command timed out after {actual_timeout} seconds",
                    )

            # Decode output
            stdout_str = process_result.stdout.decode("utf-8", errors="replace")
            stderr_str = process_result.stderr.decode("utf-8", errors="replace")

            execution_time = time.time() - start_time
            success = process_result.returncode == 0

            result = WSLCommandResult(
                command=cmd_list,
                return_code=process_result.returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                success=success,
                execution_time=execution_time,
                error=stderr_str if not success and stderr_str else None,
            )

            if success:
                logger.debug(
                    f"WSL command completed successfully in {execution_time:.2f}s"
                )
            else:
                logger.warning(
                    f"WSL command failed (code {result.return_code}) in {execution_time:.2f}s: {stderr_str}"
                )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"WSL command execution failed: {str(e)}"
            logger.error(f"{error_msg} (Command: {' '.join(wsl_command)})")
            logger.exception("Full exception details:")

            return WSLCommandResult(
                command=cmd_list,
                return_code=-1,
                stdout="",
                stderr="",
                success=False,
                execution_time=execution_time,
                error=error_msg,
            )

    async def execute_borg_command(
        self,
        borg_args: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> WSLCommandResult:
        """
        Execute a borg command through WSL.

        Args:
            borg_args: Borg command arguments (without 'borg' prefix)
            env: Environment variables
            cwd: Working directory
            timeout: Command timeout

        Returns:
            WSLCommandResult with execution details
        """
        command = ["borg"] + borg_args
        return await self.execute_command(command, env, cwd, timeout)

    async def test_connection(self) -> bool:
        """
        Test if WSL connection is working.

        Returns:
            True if WSL is accessible and working
        """
        try:
            result = await self.execute_command(["echo", "test"], timeout=5.0)
            return result.success and result.stdout.strip() == "test"
        except Exception as e:
            logger.debug(f"WSL connection test failed: {e}")
            return False

    async def get_wsl_version(self) -> Optional[str]:
        """Get the WSL version information."""
        try:
            result = await self.execute_command(["cat", "/proc/version"], timeout=5.0)
            if result.success:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    async def check_command_availability(self, command: str) -> bool:
        """
        Check if a command is available in WSL.

        Args:
            command: Command name to check

        Returns:
            True if command is available
        """
        try:
            result = await self.execute_command(["which", command], timeout=5.0)
            return result.success
        except Exception:
            return False

    def _build_wsl_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> List[str]:
        """
        Build the full WSL command with environment and working directory.

        Args:
            command: Original command to execute
            env: Environment variables
            cwd: Working directory (WSL path)

        Returns:
            Complete WSL command list
        """
        wsl_cmd = ["wsl"]

        # Add distribution if specified
        if self.distribution:
            wsl_cmd.extend(["-d", self.distribution])

        # Build the command to execute in WSL
        # We need to construct a shell command that handles env vars and cwd
        shell_parts = []

        # Set environment variables
        if env:
            for key, value in env.items():
                # Escape the value to handle special characters
                escaped_value = value.replace("'", "'\"'\"'")
                shell_parts.append(f"export {key}='{escaped_value}'")

        # Change directory if specified
        if cwd:
            shell_parts.append(f"cd '{cwd}'")

        # Add the actual command
        # Escape command arguments to handle special characters and spaces
        escaped_args = []
        for arg in command:
            if " " in arg or '"' in arg or "'" in arg:
                # Use double quotes and escape internal double quotes
                escaped_arg = '"' + arg.replace('"', '\\"') + '"'
            else:
                escaped_arg = arg
            escaped_args.append(escaped_arg)

        shell_parts.append(" ".join(escaped_args))

        # Join all parts with && to ensure they execute in sequence
        shell_command = " && ".join(shell_parts)

        # Add the shell command to WSL
        wsl_cmd.extend(["/bin/bash", "-c", shell_command])

        return wsl_cmd

    async def start_interactive_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """
        Start an interactive WSL process (for streaming operations).

        Args:
            command: Command to execute
            env: Environment variables
            cwd: Working directory

        Returns:
            Subprocess.Process for interactive communication
        """
        wsl_command = self._build_wsl_command(command, env, cwd)

        logger.debug(f"Starting interactive WSL process: {' '.join(command[:3])}...")

        process = await asyncio.create_subprocess_exec(
            *wsl_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )

        return process


# Global instance for easy access
_wsl_command_executor: Optional[WSLCommandExecutor] = None


def get_wsl_command_executor(
    distribution: Optional[str] = None, timeout: float = 300.0
) -> WSLCommandExecutor:
    """
    Get a WSL command executor instance.

    Args:
        distribution: WSL distribution to use
        timeout: Default command timeout

    Returns:
        WSLCommandExecutor instance
    """
    global _wsl_command_executor
    if (
        _wsl_command_executor is None
        or _wsl_command_executor.distribution != distribution
    ):
        _wsl_command_executor = WSLCommandExecutor(distribution, timeout)
    return _wsl_command_executor
