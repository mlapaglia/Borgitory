"""
Linux file service for native Linux file operations.
"""

import logging
import os
from typing import IO
from borgitory.protocols.file_protocols import FileServiceProtocol

logger = logging.getLogger(__name__)


class LinuxFileService(FileServiceProtocol):
    """Linux file service that uses native OS file operations."""

    async def write_file(self, file_path: str, content: bytes) -> None:
        """Write content to a file at the given path."""
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"Wrote file to {file_path}")

    async def remove_file(self, file_path: str) -> None:
        """Remove a file at the given path."""
        try:
            os.unlink(file_path)
            logger.info(f"Removed file {file_path}")
        except OSError as e:
            logger.warning(f"Failed to remove file {file_path}: {e}")

    async def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Open a file at the given path with the specified mode."""
        return open(file_path, mode)

    async def exists(self, file_path: str) -> bool:
        """Check if a file or directory exists at the given path."""
        return os.path.exists(file_path)

    async def isfile(self, file_path: str) -> bool:
        """Check if the path is a file."""
        return os.path.isfile(file_path)

    def get_platform_name(self) -> str:
        """Get the platform name this file service handles."""
        return "linux"
