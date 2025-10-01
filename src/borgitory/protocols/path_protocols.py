"""
Path service protocols for cross-platform file system operations.

This module defines the interface for path services that abstract
filesystem operations for different environments (native, WSL, container).
"""

from abc import ABC, abstractmethod
from typing import List

from borgitory.utils.secure_path import DirectoryInfo


class PathServiceInterface(ABC):
    """
    Abstract interface for filesystem path operations.

    This service abstracts filesystem operations to support different
    execution environments (native Unix, WSL on Windows, containers).
    """

    @abstractmethod
    async def get_data_dir(self) -> str:
        """Get the application data directory path."""
        pass

    @abstractmethod
    async def get_temp_dir(self) -> str:
        """Get the temporary directory path."""
        pass

    @abstractmethod
    async def get_cache_dir(self) -> str:
        """Get the cache directory path."""
        pass

    @abstractmethod
    async def get_keyfiles_dir(self) -> str:
        """Get the keyfiles directory path."""
        pass

    @abstractmethod
    async def get_mount_base_dir(self) -> str:
        """Get the base directory for archive mounts."""
        pass

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
    async def ensure_directory(self, path: str) -> None:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            path: The directory path to ensure exists

        Raises:
            OSError: If directory cannot be created
        """
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """Get the platform name (native, wsl, container)."""
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


class PathConfigurationInterface(ABC):
    """
    Interface for path configuration management.

    This service manages the configuration of base directories
    and path resolution strategies.
    """

    @abstractmethod
    def get_base_data_dir(self) -> str:
        """Get the base data directory from configuration."""
        pass

    @abstractmethod
    def get_base_temp_dir(self) -> str:
        """Get the base temp directory from configuration."""
        pass

    @abstractmethod
    def get_base_cache_dir(self) -> str:
        """Get the base cache directory from configuration."""
        pass

    @abstractmethod
    def is_docker(self) -> bool:
        """Check if running in a idocker environment."""
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """Get the platform name (windows, unix, container)."""
        pass

    @abstractmethod
    def is_windows(self) -> bool:
        """Check if running on Windows platform."""
        pass
