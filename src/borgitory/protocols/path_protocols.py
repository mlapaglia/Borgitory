"""
Path service protocols for cross-platform file system operations.

This module defines the interface for path services that abstract
filesystem operations for different environments (native, WSL, container).
"""

from abc import ABC, abstractmethod
from typing import List

from borgitory.models.borg_info import BorgDefaultDirectories
from borgitory.utils.secure_path import DirectoryInfo


class PlatformServiceProtocol(ABC):
    """
    Protocol for platform detection and identification.

    This service provides methods to identify the current platform
    and execution environment (Windows, Linux, Docker, etc.).
    """

    @abstractmethod
    def get_platform_name(self) -> str:
        """
        Get the platform name for logging and debugging.

        Returns:
            Platform name: 'windows', 'linux', 'docker', 'darwin'
        """
        pass

    @abstractmethod
    def is_docker(self) -> bool:
        """
        Check if running inside a Docker container.

        Returns:
            True if running in a Docker container
        """
        pass

    @abstractmethod
    def is_windows(self) -> bool:
        """
        Check if running on Windows.

        Returns:
            True if running on Windows
        """
        pass

    @abstractmethod
    def is_linux(self) -> bool:
        """
        Check if running on Linux.

        Returns:
            True if running on Linux
        """
        pass


class PathServiceInterface(ABC):
    """
    Abstract interface for filesystem path operations.

    This service abstracts filesystem operations to support different
    execution environments (native Unix, WSL on Windows, containers).
    """

    @abstractmethod
    def secure_join(self, base_path: str, *path_parts: str) -> str:
        """
        Securely join path components, preventing directory traversal.

        Args:
            base_path: The base directory path
            *path_parts: Additional path components to join

        Returns:
            The securely joined path
        """
        pass

    @abstractmethod
    async def path_exists(self, path: str) -> bool:
        """
        Check if a path exists.

        Args:
            path: Path to check

        Returns:
            True if path exists
        """
        pass

    @abstractmethod
    async def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory.

        Args:
            path: Path to check

        Returns:
            True if path is a directory
        """
        pass

    @abstractmethod
    async def list_directory(
        self, path: str, include_files: bool = False
    ) -> List[DirectoryInfo]:
        """
        List directory contents.

        Args:
            path: Directory path to list
            include_files: Whether to include files in results

        Returns:
            List of DirectoryInfo objects
        """
        pass

    @abstractmethod
    async def get_default_directories(self) -> BorgDefaultDirectories:
        """Get the default directories for the current environment."""
        pass
