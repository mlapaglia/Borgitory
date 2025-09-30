"""
WSL Filesystem Service for directory operations via WSL commands.

This service provides filesystem operations by executing commands through WSL,
enabling directory browsing and file operations on Windows filesystems
via the WSL /mnt/c/ interface.
"""

import logging
import re
from typing import List, Optional
from dataclasses import dataclass

from borgitory.utils.secure_path import DirectoryInfo
from .wsl_command_executor import WSLCommandExecutor

logger = logging.getLogger(__name__)


@dataclass
class WSLDirectoryInfo:
    """Extended directory information from WSL filesystem operations."""

    name: str
    path: str
    is_directory: bool
    is_borg_repo: bool = False
    is_borg_cache: bool = False
    size: Optional[int] = None
    permissions: Optional[str] = None
    modified_time: Optional[str] = None


class WSLFilesystemService:
    """Service for filesystem operations via WSL commands."""

    def __init__(self, executor: WSLCommandExecutor):
        """
        Initialize WSL filesystem service.

        Args:
            executor: WSL command executor
        """
        self.executor = executor

    async def list_directory(
        self, path: str, include_files: bool = False, include_hidden: bool = False
    ) -> List[DirectoryInfo]:
        """
        List directory contents via WSL.

        Args:
            path: Unix-style path to list (e.g., "/mnt/c/Users")
            include_files: Whether to include files in results
            include_hidden: Whether to include hidden files/directories

        Returns:
            List of DirectoryInfo objects
        """
        logger.debug(f"Listing directory via WSL: {path}")

        try:
            # Build ls command
            ls_args = ["-la"] if include_hidden else ["-l"]
            ls_args.append(path)

            result = await self.executor.execute_command(["ls"] + ls_args, timeout=30.0)

            if not result.success:
                logger.warning(f"Failed to list directory {path}: {result.error}")
                return []

            return self._parse_ls_output(result.stdout, path, include_files)

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return []

    async def path_exists(self, path: str) -> bool:
        """
        Check if a path exists via WSL.

        Args:
            path: Unix-style path to check

        Returns:
            True if path exists
        """
        try:
            result = await self.executor.execute_command(
                ["test", "-e", path], timeout=5.0
            )
            return result.success
        except Exception as e:
            logger.debug(f"Error checking path existence {path}: {e}")
            return False

    async def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory via WSL.

        Args:
            path: Unix-style path to check

        Returns:
            True if path is a directory
        """
        try:
            result = await self.executor.execute_command(
                ["test", "-d", path], timeout=5.0
            )
            return result.success
        except Exception as e:
            logger.debug(f"Error checking if directory {path}: {e}")
            return False

    async def create_directory(self, path: str, parents: bool = True) -> bool:
        """
        Create a directory via WSL.

        Args:
            path: Unix-style path to create
            parents: Create parent directories if needed

        Returns:
            True if successful
        """
        try:
            mkdir_args = ["-p", path] if parents else [path]
            result = await self.executor.execute_command(
                ["mkdir"] + mkdir_args, timeout=10.0
            )

            if result.success:
                logger.debug(f"Created directory: {path}")
                return True
            else:
                logger.warning(f"Failed to create directory {path}: {result.error}")
                return False

        except Exception as e:
            logger.error(f"Error creating directory {path}: {e}")
            return False

    async def get_available_drives(self) -> List[str]:
        """
        Get list of available Windows drives mounted in WSL.

        Returns:
            List of drive paths (e.g., ["/mnt/c", "/mnt/d"])
        """
        try:
            result = await self.executor.execute_command(["ls", "/mnt"], timeout=5.0)

            if not result.success:
                logger.warning("Failed to list /mnt directory")
                return ["/mnt/c"]  # Default fallback

            drives = []
            for line in result.stdout.strip().split("\n"):
                drive = line.strip()
                if drive and len(drive) == 1 and drive.isalpha():
                    drives.append(f"/mnt/{drive}")

            return drives if drives else ["/mnt/c"]

        except Exception as e:
            logger.error(f"Error getting available drives: {e}")
            return ["/mnt/c"]  # Default fallback

    async def get_disk_usage(self, path: str) -> Optional[dict[str, str]]:
        """
        Get disk usage information for a path via WSL.

        Args:
            path: Unix-style path to check

        Returns:
            Dictionary with usage info or None if failed
        """
        try:
            result = await self.executor.execute_command(
                ["df", "-h", path], timeout=10.0
            )

            if not result.success:
                return None

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return None

            # Parse df output (skip header line)
            parts = lines[1].split()
            if len(parts) >= 6:
                return {
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "use_percent": parts[4],
                    "mount_point": parts[5],
                }

            return None

        except Exception as e:
            logger.debug(f"Error getting disk usage for {path}: {e}")
            return None

    def _parse_ls_output(
        self, ls_output: str, base_path: str, include_files: bool
    ) -> List[DirectoryInfo]:
        """
        Parse ls -l output into DirectoryInfo objects.

        Args:
            ls_output: Output from ls -l command
            base_path: Base path being listed
            include_files: Whether to include files

        Returns:
            List of DirectoryInfo objects
        """
        items = []

        for line in ls_output.strip().split("\n"):
            if not line.strip():
                continue

            # Skip total line and current/parent directory entries
            if line.startswith("total ") or line.endswith(" .") or line.endswith(" .."):
                continue

            # Parse ls -l format: permissions links owner group size date time name
            parts = line.split(None, 8)  # Split on whitespace, max 9 parts
            if len(parts) < 9:
                continue

            permissions = parts[0]
            name = parts[8]

            # Skip hidden files unless specifically requested
            if name.startswith("."):
                continue

            is_directory = permissions.startswith("d")

            # Skip files if not requested
            if not is_directory and not include_files:
                continue

            # Build full path
            if base_path.endswith("/"):
                full_path = base_path + name
            else:
                full_path = base_path + "/" + name

            # Check for borg repository/cache indicators
            is_borg_repo = self._is_borg_repository_name(name)
            is_borg_cache = self._is_borg_cache_name(name)

            # Convert to DirectoryInfo for compatibility
            items.append(
                DirectoryInfo(
                    name=name,
                    path=full_path,
                    is_borg_repo=is_borg_repo,
                    is_borg_cache=is_borg_cache,
                )
            )

        # Sort: directories first, then alphabetically
        items.sort(
            key=lambda x: (
                not x.path.endswith("/") if hasattr(x, "path") else True,
                x.name.lower(),
            )
        )

        return items

    def _is_borg_repository_name(self, name: str) -> bool:
        """Check if directory name suggests it's a borg repository."""
        # Common borg repository naming patterns
        borg_patterns = [
            r".*\.borg$",
            r"borg[-_]?repo",
            r"backup[-_]?repo",
            r"repository",
        ]

        name_lower = name.lower()
        return any(re.match(pattern, name_lower) for pattern in borg_patterns)

    def _is_borg_cache_name(self, name: str) -> bool:
        """Check if directory name suggests it's a borg cache."""
        cache_patterns = [
            r".*cache.*",
            r"borg[-_]?cache",
            r"\.cache",
        ]

        name_lower = name.lower()
        return any(re.match(pattern, name_lower) for pattern in cache_patterns)
