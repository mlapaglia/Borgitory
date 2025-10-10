"""
Platform service for getting the platform name.
"""

import logging
import os
import platform

from borgitory.protocols.path_protocols import PlatformServiceProtocol

logger = logging.getLogger(__name__)


class PlatformService(PlatformServiceProtocol):
    """
    Platform service for getting the platform name.
    """

    def get_platform_name(self) -> str:
        """
        Get the platform name for logging and debugging.

        Returns:
            Platform name: 'windows', 'linux', 'docker', 'darwin'
        """
        if self.is_docker():
            return "docker"

        return platform.system().lower()

    def is_docker(self) -> bool:
        if os.environ.get("BORGITORY_RUNNING_IN_CONTAINER"):
            return True
        else:
            return False

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

    def get_base_data_dir(self) -> str:
        """
        Get the base data directory from configuration.

        Returns:
            The base data directory path appropriate for the current environment
        """

        env_data_dir = os.getenv("BORGITORY_DATA_DIR")
        if env_data_dir:
            return env_data_dir

        if self.is_docker():
            return "/app/data"
        elif self.is_windows():
            return os.path.expandvars("%LOCALAPPDATA%\\Borgitory")
        elif self.is_linux():
            home = os.path.expanduser("~")
            return os.path.join(home, ".local", "share", "borgitory")
        else:
            raise ValueError("Unknown platform")
