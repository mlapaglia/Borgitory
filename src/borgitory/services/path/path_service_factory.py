"""
Path service factory for creating filesystem path services.

This module provides factory functions for creating path service
implementations. Note: The main path service creation is now handled
via dependency injection in dependencies.py for better testability.
"""

import logging
import os
import subprocess

from borgitory.protocols.path_protocols import PathServiceInterface
from borgitory.services.path.path_service import PathService
from borgitory.services.command_execution.linux_command_executor import (
    LinuxCommandExecutor,
)

logger = logging.getLogger(__name__)


def wsl_available() -> bool:
    """
    Check if WSL is available on Windows.

    Returns:
        True if WSL is available and working
    """
    if os.name != "nt":
        return False

    try:
        result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def create_path_service() -> PathServiceInterface:
    """
    Create a path service for the current environment.

    Note: This is a legacy factory function. For production use,
    prefer the dependency injection approach in dependencies.py.

    Returns:
        PathServiceInterface: A path service implementation
    """

    # For factory usage, default to Linux command executor
    # In production, the proper executor is injected via DI
    command_executor = LinuxCommandExecutor()

    return PathService(command_executor)


def get_path_service() -> PathServiceInterface:
    """
    Get a path service instance.

    Note: This is a legacy function. For production use,
    prefer the dependency injection approach in dependencies.py.

    Returns:
        PathServiceInterface: A path service instance
    """
    return create_path_service()
