"""
File Service Factory for creating platform-appropriate file services.

This factory automatically detects the environment and returns the
appropriate file service implementation.
"""

import logging
import os
import subprocess

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.path.path_configuration_service import PathConfigurationService
from .linux_file_service import LinuxFileService
from .wsl_file_service import WSLFileService

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


def create_file_service(command_executor: "CommandExecutorProtocol") -> FileServiceProtocol:
    """
    Create a file service for the current environment.

    This factory function automatically detects the environment:
    - Windows with WSL: Uses WSLFileService
    - Linux/Container: Uses LinuxFileService

    Returns:
        FileServiceProtocol: A file service implementation
    """
    config = PathConfigurationService()

    if config.is_windows():
        if wsl_available():
            logger.debug("Creating WSL file service for Windows environment")
            return WSLFileService(command_executor)
        else:
            logger.error("WSL is not available on Windows environment")
            raise RuntimeError("WSL is not available on Windows environment")
    elif config.is_linux() or config.is_docker():
        logger.debug("Creating Linux file service")
        return LinuxFileService()
    else:
        logger.error(f"Unknown environment {config.get_platform_name()}, using native file service")
        raise RuntimeError(f"Unknown environment {config.get_platform_name()}")
