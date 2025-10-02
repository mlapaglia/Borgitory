"""
Command Executor Factory for creating platform-appropriate command executors.

This factory automatically detects the environment and returns the
appropriate command executor implementation.
"""

import logging
import os
import subprocess

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.services.path.path_configuration_service import PathConfigurationService
from .linux_command_executor import LinuxCommandExecutor
from .wsl_command_executor import WSLCommandExecutor

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


def create_command_executor() -> CommandExecutorProtocol:
    """
    Create a command executor for the current environment.

    This factory function automatically detects the environment:
    - Windows with WSL: Uses WSLCommandExecutor
    - Linux/Container: Uses LinuxCommandExecutor

    Returns:
        CommandExecutorProtocol: A command executor implementation
    """
    config = PathConfigurationService()

    if config.is_windows():
        if not wsl_available():
            raise RuntimeError("Detected Windows environment, but WSL is not available")

        logger.debug("Creating WSL command executor")
        return WSLCommandExecutor()
    elif config.is_linux() or config.is_docker():
        logger.debug("Creating Linux command executor")
        return LinuxCommandExecutor()
    else:
        raise RuntimeError(
            f"Unsupported environment detected: {config.get_platform_name()}"
        )


def create_command_executor_with_injection(
    wsl_executor: "WSLCommandExecutor",
) -> CommandExecutorProtocol:
    """
    Create a command executor with dependency injection.

    This version is used when WSLCommandExecutor is already injected
    via the DI system.

    Args:
        wsl_executor: Pre-configured WSL command executor

    Returns:
        CommandExecutorProtocol: A command executor implementation
    """
    config = PathConfigurationService()

    if config.is_windows() and wsl_available():
        logger.debug("Using injected WSL command executor for Windows environment")
        return wsl_executor
    else:
        platform = config.get_platform_name()
        logger.debug(f"Creating Unix command executor for {platform} environment")
        return LinuxCommandExecutor()
