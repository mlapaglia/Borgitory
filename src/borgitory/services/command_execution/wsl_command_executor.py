"""
WSL Command Executor for running commands through Windows Subsystem for Linux.

This service provides a wrapper around subprocess execution that routes
all commands through WSL, enabling Unix-style command execution on Windows.
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


class WSLCommandExecutor(CommandExecutorProtocol):
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
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        input_data: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute a command through WSL.

        Args:
            command: Command to execute (string or list)
            env: Environment variables to set
            cwd: Working directory (WSL path)
            timeout: Command timeout in seconds
            input_data: Data to send to command stdin

        Returns:
            CommandResult with execution details
        """
        start_time = time.time()

        # Command is already a list from the protocol
        cmd_list = list(command)

        # Build WSL command
        wsl_command = self._build_wsl_command(cmd_list, env, cwd)

        actual_timeout = timeout or self.default_timeout

        logger.debug(
            f"Executing WSL command: {' '.join(wsl_command[:3])}... (timeout: {actual_timeout}s)"
        )

        try:
            # Use asyncio.create_subprocess_exec directly
            process = await asyncio.create_subprocess_exec(
                *wsl_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else None,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(
                        input=input_data.encode() if input_data else None
                    ),
                    timeout=actual_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                execution_time = time.time() - start_time
                return CommandResult(
                    command=cmd_list,
                    return_code=-1,
                    stdout="",
                    stderr="",
                    success=False,
                    execution_time=execution_time,
                    error=f"Command timed out after {actual_timeout} seconds",
                )

            # Decode output
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            execution_time = time.time() - start_time
            success = process.returncode == 0

            result = CommandResult(
                command=cmd_list,
                return_code=process.returncode or 0,
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
                if "No such file or directory" not in stderr_str:
                    logger.warning(
                        f"WSL command failed (code {result.return_code}) in {execution_time:.2f}s: {stderr_str}"
                    )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"WSL command execution failed: {str(e)}"
            logger.error(f"{error_msg} (Command: {' '.join(wsl_command)})")
            logger.exception("Full exception details:")

            return CommandResult(
                command=cmd_list,
                return_code=-1,
                stdout="",
                stderr="",
                success=False,
                execution_time=execution_time,
                error=error_msg,
            )

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
        # Special case: if command starts with "wsl.exe", execute it directly
        # This allows running Windows commands from inside WSL
        if command and command[0] == "wsl.exe":
            return command

        wsl_cmd = ["wsl"]

        # Add distribution if specified
        if self.distribution:
            wsl_cmd.extend(["-d", self.distribution])

        # Build the command to execute in WSL
        # We need to construct a shell command that handles env vars and cwd
        shell_parts = []

        # Set environment variables (only pass relevant ones to avoid bash syntax errors)
        if env:
            # Filter to only pass variables that are relevant for our commands
            relevant_prefixes = [
                "BORG_",  # All Borg-related variables
                "BORGITORY_",  # Our app-specific variables
            ]

            for key, value in env.items():
                # Only pass environment variables that are relevant
                if any(key.startswith(prefix) for prefix in relevant_prefixes):
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

        # Add the shell command to WSL using login shell (-l) to get full environment
        wsl_cmd.extend(["/bin/bash", "-l", "-c", shell_command])

        return wsl_cmd

    async def create_subprocess(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdout: Optional[int] = None,
        stderr: Optional[int] = None,
        stdin: Optional[int] = None,
    ) -> asyncio.subprocess.Process:
        """
        Create a subprocess for streaming operations.

        Args:
            command: Command to execute
            env: Environment variables
            cwd: Working directory
            stdout: Stdout redirection (e.g., asyncio.subprocess.PIPE)
            stderr: Stderr redirection (e.g., asyncio.subprocess.PIPE)
            stdin: Stdin redirection (e.g., asyncio.subprocess.PIPE)

        Returns:
            Process object for streaming operations
        """
        wsl_command = self._build_wsl_command(command, env, cwd)

        logger.debug(f"Starting interactive WSL process: {' '.join(command[:3])}...")

        process = await asyncio.create_subprocess_exec(
            *wsl_command,
            stdout=stdout or asyncio.subprocess.PIPE,
            stderr=stderr or asyncio.subprocess.PIPE,
            stdin=stdin,
            env=env,
            cwd=cwd,
        )

        return process

    def get_platform_name(self) -> str:
        """Get the platform name this executor handles."""
        return "wsl"
