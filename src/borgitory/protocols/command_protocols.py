"""
Protocol interfaces for command execution services.
"""

from typing import Protocol, Dict, Optional, List, Callable, Any
import asyncio


class CommandResult:
    """Result of a command execution."""

    def __init__(self, success: bool, return_code: int, stdout: str, stderr: str, duration: float, error: Optional[str] = None):
        self.success = success
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration
        self.error = error


class ProcessResult:
    """Result of a process execution."""

    def __init__(self, return_code: int, stdout: bytes, stderr: bytes, error: Optional[str] = None):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.error = error


class CommandRunnerProtocol(Protocol):
    """Protocol for command execution services."""

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Execute a command and return the result."""
        ...


class ProcessExecutorProtocol(Protocol):
    """Protocol for process execution services."""

    async def start_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """Start a process and return the process handle."""
        ...

    async def monitor_process_output(
        self,
        process: asyncio.subprocess.Process,
        output_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> "ProcessResult":
        """Monitor a process and return the result when complete."""
        ...
