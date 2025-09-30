"""
Command Execution package for cross-platform command execution.

This package provides command executors for different environments
and a factory for creating the appropriate executor.
"""

from .unix_command_executor import UnixCommandExecutor
from .command_executor_factory import create_command_executor

__all__ = [
    "UnixCommandExecutor",
    "create_command_executor",
]
