"""
Path configuration service for managing Unix/WSL directory settings.

This service handles the configuration and detection of base directories
for Unix and container environments. Windows is only supported via WSL.
"""

import os
import logging
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
        self._is_container: Optional[bool] = None

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
        if self.is_container_environment():
            return "/app/data"
        else:  # Unix-like systems (including WSL)
            # Check for XDG_DATA_HOME (Linux standard)
            xdg_data = os.getenv("XDG_DATA_HOME")
            if xdg_data:
                return os.path.join(xdg_data, "borgitory")

            # Check if running as root (Unix only)
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                return "/var/lib/borgitory"

            # User installation - use ~/.local/share
            home = os.path.expanduser("~")
            return os.path.join(home, ".local", "share", "borgitory")

    def get_base_temp_dir(self) -> str:
        """
        Determine the base temporary directory for Borgitory.
        Prioritizes environment variable, then platform-specific defaults.
        """
        env_temp_dir = os.getenv("BORGITORY_TEMP_DIR")
        if env_temp_dir:
            return env_temp_dir

        if self._is_container:
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

        if self._is_container:
            return "/cache/borgitory"  # Matches Docker volume mount
        else:  # Unix-like (including WSL)
            # Check for XDG_CACHE_HOME (Linux standard)
            xdg_cache = os.getenv("XDG_CACHE_HOME")
            if xdg_cache:
                return os.path.join(xdg_cache, "borgitory")
            home = os.path.expanduser("~")
            return os.path.join(home, ".cache", "borgitory")

    def is_container_environment(self) -> bool:
        """
        Check if running in a container environment.

        Returns:
            True if running in a container
        """
        if self._is_container is not None:
            return self._is_container

        # Check multiple container indicators
        container_indicators = [
            # Docker
            os.path.exists("/.dockerenv"),
            # Kubernetes
            os.getenv("KUBERNETES_SERVICE_HOST") is not None,
            # Generic container indicators
            os.getenv("CONTAINER") == "true",
            os.getenv("DOCKER_CONTAINER") == "true",
            # Check if we're running in /app (common container pattern)
            os.getcwd().startswith("/app"),
        ]

        self._is_container = any(container_indicators)

        if self._is_container:
            logger.info("Container environment detected")
        else:
            logger.info(f"Native environment detected: {os.name}")

        return self._is_container

    def get_platform_name(self) -> str:
        """
        Get the platform name for logging and debugging.

        Returns:
            Platform name: 'container' or 'unix' (Windows only supported via WSL)
        """
        if self._platform_name is not None:
            return self._platform_name

        if self.is_container_environment():
            self._platform_name = "container"
        else:
            # All non-container environments are treated as Unix
            # Windows is only supported via WSL which appears as Unix
            self._platform_name = "unix"

        return self._platform_name

    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if running on Windows
        """
        return os.name == "nt"
