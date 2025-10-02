"""
Command Executor Protocol for cross-platform command execution.

This protocol defines the interface for executing system commands
across different environments (Unix/Linux, Docker, Windows WSL).
"""

import asyncio
from typing import Protocol, List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of a command execution."""

    command: List[str]
    return_code: int
    stdout: str
    stderr: str
    success: bool
    execution_time: float
    error: Optional[str] = None


class CommandExecutorProtocol(Protocol):
    """Protocol for executing system commands across different environments."""

    async def execute_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        input_data: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute a command and return the result.

        Args:
            command: Command and arguments to execute
            env: Environment variables to set
            cwd: Working directory for the command
            timeout: Command timeout in seconds
            input_data: Data to send to command stdin

        Returns:
            CommandResult with execution details
        """
        ...

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

        This method is needed for long-running processes where we need
        to stream output in real-time (like backup operations).

        Args:
            command: Command and arguments to execute
            env: Environment variables to set
            cwd: Working directory for the command
            stdout: Stdout redirection (e.g., asyncio.subprocess.PIPE)
            stderr: Stderr redirection (e.g., asyncio.subprocess.PIPE)
            stdin: Stdin redirection (e.g., asyncio.subprocess.PIPE)

        Returns:
            Process object for streaming operations
        """
        ...

    def get_platform_name(self) -> str:
        """
        Get the platform name this executor handles.

        Returns:
            Platform name (e.g., 'unix', 'wsl', 'container')
        """
        ...
