"""
WSL-aware file service for cross-platform file operations.
"""

import logging
import io
from typing import IO
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol

logger = logging.getLogger(__name__)


class WSLFileService(FileServiceProtocol):
    """WSL-aware file service that uses WSL commands for file operations."""

    def __init__(self, command_executor: CommandExecutorProtocol):
        self.command_executor = command_executor

    async def write_file(self, file_path: str, content: bytes) -> None:
        """Write content to a file at the given path using WSL."""
        # Use WSL to write the file
        result = await self.command_executor.execute_command(
            command=["sh", "-c", f"cat > '{file_path}'"],
            input_data=content.decode('utf-8'),
            timeout=30.0
        )
        
        if not result.success:
            raise Exception(f"Failed to write file {file_path}: {result.stderr}")
        
        logger.info(f"Wrote file to {file_path} via WSL")

    async def remove_file(self, file_path: str) -> None:
        """Remove a file at the given path using WSL."""
        result = await self.command_executor.execute_command(
            command=["rm", "-f", file_path],
            timeout=30.0
        )
        
        if not result.success:
            logger.warning(f"Failed to remove file {file_path}: {result.stderr}")
        else:
            logger.info(f"Removed file {file_path} via WSL")

    async def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Open a file at the given path with the specified mode."""
        if mode == "rb":
            # Read binary mode - use cat to read the file
            result = await self.command_executor.execute_command(
                command=["cat", file_path],
                timeout=30.0
            )
            
            if not result.success:
                raise FileNotFoundError(f"Failed to read file {file_path}: {result.stderr}")
            
            # Return the content as a BytesIO object
            return io.BytesIO(result.stdout.encode('utf-8'))
        
        elif mode == "r":
            # Read text mode - use cat to read the file
            result = await self.command_executor.execute_command(
                command=["cat", file_path],
                timeout=30.0
            )
            
            if not result.success:
                raise FileNotFoundError(f"Failed to read file {file_path}: {result.stderr}")
            
            # Return the content as a StringIO object wrapped in BytesIO
            return io.BytesIO(result.stdout.encode('utf-8'))
        
        else:
            # For write modes, we can't easily implement a file-like object
            # The caller should use write_file instead
            raise NotImplementedError(f"WSL file service does not support mode '{mode}'. Use write_file() for writing.")

    async def exists(self, file_path: str) -> bool:
        """Check if a file or directory exists at the given path using WSL."""
        result = await self.command_executor.execute_command(
            command=["test", "-e", file_path],
            timeout=10.0
        )
        return result.success

    async def isfile(self, file_path: str) -> bool:
        """Check if the path is a file using WSL."""
        result = await self.command_executor.execute_command(
            command=["test", "-f", file_path],
            timeout=10.0
        )
        return result.success

    def get_platform_name(self) -> str:
        """Get the platform name this file service handles."""
        return "wsl"
