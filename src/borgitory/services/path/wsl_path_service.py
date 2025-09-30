"""
WSL Path Service implementation.

This service extends UniversalPathService to use WSL commands for all
filesystem operations on Windows, enabling seamless Unix-style operations.
"""

import logging
from typing import List

from borgitory.utils.secure_path import DirectoryInfo
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.services.path.universal_path_service import UniversalPathService
from borgitory.services.wsl.wsl_command_executor import WSLCommandExecutor

logger = logging.getLogger(__name__)


class WSLPathService(UniversalPathService):
    """
    WSL-aware path service implementation.

    This service uses WSL commands for all filesystem operations,
    enabling Unix-style path handling on Windows systems.
    """

    def __init__(
        self, config: PathConfigurationService, wsl_executor: WSLCommandExecutor
    ):
        super().__init__(config)
        self.wsl_executor = wsl_executor
        logger.debug("Initialized WSL path service")

    async def get_data_dir(self) -> str:
        """Get the application data directory (WSL-style path)."""
        # Override to return WSL-style paths instead of Windows paths
        data_dir = (
            "/mnt/c/Users/" + self._get_current_user() + "/.local/share/borgitory"
        )
        await self.ensure_directory(data_dir)
        return data_dir

    async def get_temp_dir(self) -> str:
        """Get the temporary directory (WSL-style path)."""
        temp_dir = "/tmp/borgitory"
        await self.ensure_directory(temp_dir)
        return temp_dir

    async def get_cache_dir(self) -> str:
        """Get the cache directory (WSL-style path)."""
        cache_dir = "/mnt/c/Users/" + self._get_current_user() + "/.cache/borgitory"
        await self.ensure_directory(cache_dir)
        return cache_dir

    def _get_current_user(self) -> str:
        """Get the current Windows username for WSL paths."""
        import os

        return os.getenv("USERNAME", "user")

    def secure_join(self, base_path: str, *path_parts: str) -> str:
        """
        Securely join Unix-style path components.

        This override ensures we use Unix-style path joining for WSL paths.
        """
        if not base_path:
            raise ValueError("Base path cannot be empty for secure_join.")

        # For WSL, we work with Unix paths exclusively
        import posixpath

        # Normalize the base path
        validated_base = posixpath.normpath(base_path)

        # Join path parts without cleaning first (to detect traversal)
        if not path_parts:
            return validated_base

        # Filter out empty parts
        filtered_parts = [part for part in path_parts if part and part.strip()]
        if not filtered_parts:
            return validated_base

        # Join with the validated base using posix path semantics
        joined_path = validated_base
        for part in filtered_parts:
            joined_path = posixpath.join(joined_path, part)

        final_path = posixpath.normpath(joined_path)

        # Validate the final result is still under the base directory
        # Convert to absolute paths for comparison
        if not posixpath.isabs(validated_base):
            validated_base = posixpath.abspath(validated_base)
        if not posixpath.isabs(final_path):
            final_path = posixpath.abspath(final_path)

        # Check if final path starts with base path
        if (
            not final_path.startswith(validated_base + "/")
            and final_path != validated_base
        ):
            logger.error(
                f"Path traversal detected: {final_path} not under {validated_base}"
            )
            raise ValueError(
                "Invalid path operation: resulting path is outside the allowed base directory."
            )

        return final_path

    def get_platform_name(self) -> str:
        """Get the platform name (always 'wsl' for this service)."""
        return "wsl"

    async def path_exists(self, path: str) -> bool:
        """
        Check if a path exists using WSL.

        Args:
            path: Unix-style path to check

        Returns:
            True if path exists
        """
        try:
            result = await self.wsl_executor.execute_command(
                ["test", "-e", path], timeout=5.0
            )
            return result.success
        except Exception as e:
            logger.debug(f"Error checking path existence {path}: {e}")
            return False

    async def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory using WSL.

        Args:
            path: Unix-style path to check

        Returns:
            True if path is a directory
        """
        try:
            result = await self.wsl_executor.execute_command(
                ["test", "-d", path], timeout=5.0
            )
            return result.success
        except Exception as e:
            logger.debug(f"Error checking if directory {path}: {e}")
            return False

    async def list_directory(
        self, path: str, include_files: bool = False
    ) -> List[DirectoryInfo]:
        """
        List directory contents using WSL.

        Args:
            path: Unix-style path to list
            include_files: Whether to include files in results

        Returns:
            List of DirectoryInfo objects
        """
        logger.debug(f"Listing directory via WSL: {path}")

        try:
            result = await self.wsl_executor.execute_command(
                ["ls", "-la", path], timeout=30.0
            )

            # Even if ls returns non-zero due to permission errors on some files,
            # we can still parse the successful entries from stdout
            if not result.success and not result.stdout.strip():
                # Only fail if there's no output at all
                logger.warning(f"Failed to list directory {path}: {result.error}")
                return []
            elif not result.success:
                # Log permission warnings but continue with partial results
                logger.debug(
                    f"Partial directory listing for {path} (some permission denied): {result.error}"
                )

            return self._parse_ls_output(result.stdout, path, include_files)

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return []

    async def ensure_directory(self, path: str) -> None:
        """
        Ensure a directory exists using WSL, creating it if necessary.

        Args:
            path: Unix-style path to ensure exists

        Raises:
            OSError: If directory cannot be created
        """
        if not path:
            return

        try:
            result = await self.wsl_executor.execute_command(
                ["mkdir", "-p", path], timeout=10.0
            )

            if result.success:
                logger.debug(f"Ensured directory exists: {path}")
            else:
                error_msg = f"Failed to create directory {path}: {result.error}"
                logger.error(error_msg)
                raise OSError(error_msg)

        except Exception as e:
            if isinstance(e, OSError):
                raise
            logger.error(f"Error ensuring directory {path}: {e}")
            raise OSError(f"Failed to ensure directory {path}: {str(e)}")

    async def get_available_drives(self) -> List[str]:
        """
        Get list of available Windows drives mounted in WSL.

        Returns:
            List of drive paths (e.g., ["/mnt/c", "/mnt/d"])
        """
        try:
            result = await self.wsl_executor.execute_command(
                ["ls", "/mnt"], timeout=5.0
            )

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

    def _parse_ls_output(
        self, ls_output: str, base_path: str, include_files: bool
    ) -> List[DirectoryInfo]:
        """
        Parse ls -la output into DirectoryInfo objects.

        Args:
            ls_output: Output from ls -la command
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

            # Parse ls -la format: permissions links owner group size date time name
            parts = line.split(None, 8)  # Split on whitespace, max 9 parts
            if len(parts) < 9:
                continue

            permissions = parts[0]
            name = parts[8]

            # Skip hidden files (starting with .)
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
            key=lambda x: (not self._is_likely_directory(x.path), x.name.lower())
        )

        return items

    def _is_borg_repository_name(self, name: str) -> bool:
        """Check if directory name suggests it's a borg repository."""
        import re

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
        import re

        cache_patterns = [
            r".*cache.*",
            r"borg[-_]?cache",
            r"\.cache",
        ]

        name_lower = name.lower()
        return any(re.match(pattern, name_lower) for pattern in cache_patterns)

    def _is_likely_directory(self, path: str) -> bool:
        """Simple heuristic to determine if path is likely a directory."""
        # This is a simple heuristic since we're sorting
        # In practice, we know from the ls parsing whether it's a directory
        return not path.endswith(
            (".txt", ".log", ".json", ".xml", ".zip", ".tar", ".gz")
        )

    async def test_wsl_connectivity(self) -> bool:
        """
        Test if WSL connectivity is working.

        Returns:
            True if WSL is accessible and working
        """
        try:
            result = await self.wsl_executor.execute_command(
                ["echo", "test"], timeout=5.0
            )
            return result.success and result.stdout.strip() == "test"
        except Exception as e:
            logger.debug(f"WSL connectivity test failed: {e}")
            return False
