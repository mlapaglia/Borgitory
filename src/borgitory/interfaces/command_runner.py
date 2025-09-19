"""
Command runner protocol interface.

Defines the contract for command execution services.
"""

from typing import Protocol, List, Dict, Optional, NamedTuple


class CommandResult(NamedTuple):
    """Result of a command execution"""

    success: bool
    return_code: int
    stdout: str
    stderr: str
    duration: float
    error: Optional[str] = None


class CommandRunner(Protocol):
    """Protocol for command execution services"""

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
            timeout: Command timeout in seconds

        Returns:
            CommandResult with execution details
        """
        ...
