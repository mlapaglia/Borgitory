"""
Linux file service for native Linux file operations.
"""

import asyncio
import logging
import os
from typing import IO, AsyncIterator
from contextlib import asynccontextmanager
from borgitory.protocols.file_protocols import FileServiceProtocol
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class LinuxFileService(FileServiceProtocol):
    """Linux file service that uses native OS file operations."""

    @asynccontextmanager
    async def create_temp_file(
        self, suffix: str, content: Optional[bytes] = None
    ) -> AsyncIterator[str]:
        """Create a temporary file with the given suffix. Returns a context manager that yields the file path."""
        temp_path = await asyncio.to_thread(self._create_empty_temp_file, suffix)

        logger.info(f"Created temp file at {temp_path}")

        if content:
            await self.write_file(temp_path, content)

        try:
            yield temp_path
        finally:
            await self.remove_file(temp_path)

    @staticmethod
    def _create_empty_temp_file(suffix: str) -> str:
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_file.close()
        return temp_file.name

    @staticmethod
    def _write_file_sync(file_path: str, content: bytes) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)

    async def write_file(self, file_path: str, content: bytes) -> None:
        """Write content to a file at the given path (off the event loop)."""
        await asyncio.to_thread(self._write_file_sync, file_path, content)
        logger.info(f"Wrote file to {file_path}")

    async def remove_file(self, file_path: str) -> None:
        """Remove a file at the given path."""
        try:
            await asyncio.to_thread(os.unlink, file_path)
            logger.info(f"Removed file {file_path}")
        except OSError as e:
            logger.warning(f"Failed to remove file {file_path}: {e}")

    async def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Open a file at the given path with the specified mode."""
        return await asyncio.to_thread(open, file_path, mode)

    async def exists(self, file_path: str) -> bool:
        """Check if a file or directory exists at the given path."""
        return await asyncio.to_thread(os.path.exists, file_path)

    async def isfile(self, file_path: str) -> bool:
        """Check if the path is a file."""
        return await asyncio.to_thread(os.path.isfile, file_path)

    def get_platform_name(self) -> str:
        """Get the platform name this file service handles."""
        return "linux"
