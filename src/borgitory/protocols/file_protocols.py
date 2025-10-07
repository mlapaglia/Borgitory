"""
Protocol interfaces for file operations.
"""

from typing import Protocol, IO
from abc import abstractmethod


class FileServiceProtocol(Protocol):
    """Protocol for file operations."""

    @abstractmethod
    async def write_file(self, file_path: str, content: bytes) -> None:
        """Write content to a file at the given path."""
        ...

    @abstractmethod
    async def remove_file(self, file_path: str) -> None:
        """Remove a file at the given path."""
        ...

    @abstractmethod
    async def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Open a file at the given path with the specified mode."""
        ...

    @abstractmethod
    async def exists(self, file_path: str) -> bool:
        """Check if a file or directory exists at the given path."""
        ...

    @abstractmethod
    async def isfile(self, file_path: str) -> bool:
        """Check if the path is a file."""
        ...

    @abstractmethod
    def get_platform_name(self) -> str:
        """Get the platform name this file service handles."""
        ...
