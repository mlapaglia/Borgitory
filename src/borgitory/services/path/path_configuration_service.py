"""
Path configuration service for managing Unix/WSL directory settings.

This service handles the configuration and detection of base directories
for Unix and container environments. Windows is only supported via WSL.
"""

import os
import platform
import logging
from os import path
from typing import Optional

from borgitory.protocols.path_protocols import PathConfigurationInterface

logger = logging.getLogger(__name__)


class PathConfigurationService(PathConfigurationInterface):
    """
    Service for managing path configuration across Unix environments.

    This service detects the runtime environment and provides appropriate
    base directory configurations for Unix and container environments.
    Windows is only supported via WSL.
    """

    def __init__(self) -> None:
        """Initialize the path configuration service."""
        self._platform_name: Optional[str] = None
        self._is_docker: Optional[bool] = None

    def get_base_data_dir(self) -> str:
        """
        Get the base data directory from configuration.

        Returns:
            The base data directory path appropriate for the current environment
        """
        # Check for explicit environment variable first
        env_data_dir = os.getenv("BORGITORY_DATA_DIR")
        if env_data_dir:
            return env_data_dir

        # Use environment-specific defaults
        if self.is_docker():
            return "/app/data"
        elif self.is_windows():
            return path.expandvars("%LOCALAPPDATA%\\Borgitory")
        elif self.is_linux():
            home = os.path.expanduser("~")
            return os.path.join(home, ".local", "share", "borgitory")
        else:
            raise ValueError("Unknown platform")

    def get_base_temp_dir(self) -> str:
        """
        Determine the base temporary directory for Borgitory.
        Prioritizes environment variable, then platform-specific defaults.
        """
        env_temp_dir = os.getenv("BORGITORY_TEMP_DIR")
        if env_temp_dir:
            return env_temp_dir

        if self._is_docker:
            return "/tmp/borgitory"
        else:  # Unix-like (including WSL)
            return "/tmp/borgitory"

    def get_base_cache_dir(self) -> str:
        """
        Determine the base cache directory for Borgitory.
        Prioritizes environment variable, then platform-specific defaults.
        """
        env_cache_dir = os.getenv("BORGITORY_CACHE_DIR")
        if env_cache_dir:
            return env_cache_dir

        if self._is_docker:
            return "/cache/borgitory"  # Matches Docker volume mount
        else:  # Unix-like (including WSL)
            # Check for XDG_CACHE_HOME (Linux standard)
            xdg_cache = os.getenv("XDG_CACHE_HOME")
            if xdg_cache:
                return os.path.join(xdg_cache, "borgitory")
            home = os.path.expanduser("~")
            return os.path.join(home, ".cache", "borgitory")

    def is_docker(self) -> bool:
        if os.environ.get("BORGITORY_RUNNING_IN_CONTAINER"):
            return True
        else:
            return False

    def get_platform_name(self) -> str:
        """
        Get the platform name for logging and debugging.

        Returns:
            Platform name: 'windows', 'linux', 'docker', 'darwin'
        """
        if self._platform_name is not None:
            return self._platform_name

        if self.is_docker():
            return "docker"

        return platform.system().lower()

    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if running on Windows
        """
        return self.get_platform_name() == "windows"

    def is_linux(self) -> bool:
        """
        Check if running on Linux.

        Returns:
            True if running on Linux
        """
        return self.get_platform_name() == "linux"
