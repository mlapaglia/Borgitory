"""
File service implementation for file operations.
"""

import logging
import os
from typing import IO
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.utils.secure_path import secure_remove_file

logger = logging.getLogger(__name__)


class FileService(FileServiceProtocol):
    """Concrete implementation of file operations."""

    async def write_file(self, file_path: str, content: bytes) -> None:
        """Write content to a file at the given path."""
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"Wrote file to {file_path}")

    async def remove_file(self, file_path: str) -> None:
        """Remove a file at the given path."""
        secure_remove_file(file_path)
        logger.info(f"Removed file {file_path}")

    def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Open a file at the given path with the specified mode."""
        return open(file_path, mode)

    def exists(self, file_path: str) -> bool:
        """Check if a file or directory exists at the given path."""
        return os.path.exists(file_path)

    def isfile(self, file_path: str) -> bool:
        """Check if the path is a file."""
        return os.path.isfile(file_path)
