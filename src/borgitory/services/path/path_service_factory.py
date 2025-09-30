"""
Path service factory for creating filesystem path services.

This module provides the factory function for creating path service
implementations for different environments.
"""

import logging
import os
import subprocess

from borgitory.protocols.path_protocols import PathServiceInterface
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.services.path.universal_path_service import UniversalPathService

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

    This factory function automatically detects the environment:
    - Windows with WSL: Uses WSLPathService
    - Unix/Container: Uses UniversalPathService

    Returns:
        PathServiceInterface: A path service implementation
    """
    config = PathConfigurationService()

    # Note: WSL path service creation is now handled in dependencies.py with DI
    # This factory now only creates UniversalPathService
    platform = config.get_platform_name()
    logger.info(f"Creating universal path service for {platform} environment")
    return UniversalPathService(config)


def get_path_service() -> PathServiceInterface:
    """
    Get a path service instance.

    This function is designed to be used with FastAPI's dependency injection system.

    Returns:
        PathServiceInterface: A path service instance
    """
    return create_path_service()
