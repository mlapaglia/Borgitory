"""
Unified path service implementation.

This service provides filesystem operations that work across different
environments by using the appropriate CommandExecutorProtocol implementation.
"""

import logging
import posixpath
from typing import List, Tuple

from borgitory.protocols.path_protocols import PathServiceInterface
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.utils.secure_path import DirectoryInfo

logger = logging.getLogger(__name__)


class PathService(PathServiceInterface):
    """
    Unified path service implementation.

    This service provides filesystem operations that work across different
    environments by using the injected CommandExecutorProtocol for all
    filesystem operations.
    """

    def __init__(
        self,
        config: PathConfigurationService,
        command_executor: CommandExecutorProtocol,
    ):
        self.config = config
        self.command_executor = command_executor
        logger.debug(
            f"Initialized path service for {config.get_platform_name()} with {type(command_executor).__name__}"
        )

    async def get_data_dir(self) -> str:
        """Get the application data directory."""
        if self.config.is_windows():
            # Use WSL-style paths for Windows
            data_dir = (
                "/mnt/c/Users/" + self._get_current_user() + "/.local/share/borgitory"
            )
        else:
            # Use native paths for Unix systems
            data_dir = self.config.get_base_data_dir()

        await self.ensure_directory(data_dir)
        return data_dir

    async def get_temp_dir(self) -> str:
        """Get the temporary directory."""
        if self.config.is_windows():
            # Use WSL temp directory for Windows
            temp_dir = "/tmp/borgitory"
        else:
            # Use configured temp directory for Unix systems
            temp_dir = self.config.get_base_temp_dir()

        await self.ensure_directory(temp_dir)
        return temp_dir

    async def get_cache_dir(self) -> str:
        """Get the cache directory."""
        if self.config.is_windows():
            # Use WSL-style paths for Windows
            cache_dir = "/mnt/c/Users/" + self._get_current_user() + "/.cache/borgitory"
        else:
            # Use configured cache directory for Unix systems
            cache_dir = self.config.get_base_cache_dir()

        await self.ensure_directory(cache_dir)
        return cache_dir

    async def get_keyfiles_dir(self) -> str:
        """Get the keyfiles directory."""
        data_dir = await self.get_data_dir()
        keyfiles_dir = self.secure_join(data_dir, "keyfiles")
        await self.ensure_directory(keyfiles_dir)
        return keyfiles_dir

    async def get_mount_base_dir(self) -> str:
        """Get the base directory for archive mounts."""
        temp_dir = await self.get_temp_dir()
        mount_dir = self.secure_join(temp_dir, "borgitory-mounts")
        await self.ensure_directory(mount_dir)
        return mount_dir

    def _get_current_user(self) -> str:
        """Get the current Windows username for WSL paths."""
        import os

        return os.getenv("USERNAME", "user")

    def secure_join(self, base_path: str, *path_parts: str) -> str:
        """
        Securely join path components and validate the result.

        Uses Unix-style path joining for consistency across platforms.
        """
        if not base_path:
            raise ValueError("Base path cannot be empty for secure_join.")

        # Use Unix path semantics for consistency
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
        """Get the platform name from configuration."""
        return self.config.get_platform_name()

    async def path_exists(self, path: str) -> bool:
        """
        Check if a path exists using the command executor.

        Args:
            path: Path to check

        Returns:
            True if path exists
        """
        try:
            result = await self.command_executor.execute_command(
                ["test", "-e", path], timeout=5.0
            )
            return result.success
        except Exception as e:
            logger.debug(f"Error checking path existence {path}: {e}")
            return False

    async def is_directory(self, path: str) -> bool:
        """
        Check if a path is a directory using the command executor.

        Args:
            path: Path to check

        Returns:
            True if path is a directory
        """
        try:
            result = await self.command_executor.execute_command(
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
        List directory contents using the command executor.

        Args:
            path: Path to list
            include_files: Whether to include files in results

        Returns:
            List of DirectoryInfo objects
        """
        logger.debug(f"Listing directory: {path}")

        try:
            result = await self.command_executor.execute_command(
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

            return await self._parse_ls_output(result.stdout, path, include_files)

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return []

    async def ensure_directory(self, path: str) -> None:
        """
        Ensure a directory exists using the command executor, creating it if necessary.

        Args:
            path: Path to ensure exists

        Raises:
            OSError: If directory cannot be created
        """
        if not path:
            return

        try:
            result = await self.command_executor.execute_command(
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
        Get list of available drives.

        For Windows: Returns WSL-mounted drives (e.g., ["/mnt/c", "/mnt/d"])
        For Unix: Returns root filesystem ["/"]

        Returns:
            List of drive paths
        """
        if self.config.is_windows():
            try:
                result = await self.command_executor.execute_command(
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
        else:
            # Unix systems typically have a single root filesystem
            return ["/"]

    async def _parse_ls_output(
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
        directories_to_check = []

        # First pass: collect basic directory info
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

            # Create basic DirectoryInfo
            dir_info = DirectoryInfo(
                name=name,
                path=full_path,
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            )
            items.append(dir_info)

            # Collect directories for batch Borg checking
            if is_directory:
                directories_to_check.append((dir_info, full_path))

        # Second pass: batch check for Borg repositories/caches
        if directories_to_check:
            await self._batch_check_borg_directories(directories_to_check)

        # Sort: directories first, then alphabetically
        items.sort(
            key=lambda x: (
                not x.path.endswith("/") if hasattr(x, "path") else True,
                x.name.lower(),
            )
        )

        return items

    async def _batch_check_borg_directories(
        self, directories_to_check: List[Tuple[DirectoryInfo, str]]
    ) -> None:
        """
        Batch check multiple directories for Borg repository/cache indicators.

        This is much faster than individual checks as it uses a single command.

        Args:
            directories_to_check: List of (DirectoryInfo, path) tuples to check
        """
        if not directories_to_check:
            return

        # Build a single command that checks all directories at once
        # Use find to locate config files and grep to check their content
        paths = [path for _, path in directories_to_check]

        # Create a command that:
        # 1. Finds all config files in the directories
        # 2. Checks their content for [repository] or [cache] sections
        # 3. Handles permission errors gracefully

        find_configs_cmd = (
            ["find"]
            + paths
            + [
                "-maxdepth",
                "1",
                "-name",
                "config",
                "-type",
                "f",
                "-exec",
                "sh",
                "-c",
                "for file; do "
                'if head -20 "$file" 2>/dev/null | grep -q "\\[repository\\]"; then '
                'echo "REPO:$file"; '
                'elif head -20 "$file" 2>/dev/null | grep -q "\\[cache\\]"; then '
                'echo "CACHE:$file"; '
                "fi; "
                "done",
                "_",
                "{}",
                "+",
            ]
        )

        try:
            result = await self.command_executor.execute_command(
                find_configs_cmd, timeout=10.0
            )

            # Parse results and update DirectoryInfo objects
            if result.success and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    if line.startswith("REPO:"):
                        config_path = line[5:]  # Remove "REPO:" prefix
                        dir_path = config_path.rsplit("/", 1)[0]  # Get directory path
                        self._mark_directory_as_borg_repo(
                            directories_to_check, dir_path
                        )
                    elif line.startswith("CACHE:"):
                        config_path = line[6:]  # Remove "CACHE:" prefix
                        dir_path = config_path.rsplit("/", 1)[0]  # Get directory path
                        self._mark_directory_as_borg_cache(
                            directories_to_check, dir_path
                        )

            # Check for permission errors in stderr
            if result.stderr and "Permission denied" in result.stderr:
                # Parse stderr to identify which directories have permission issues
                for line in result.stderr.split("\n"):
                    if "Permission denied" in line:
                        # Extract directory path from error message
                        for dir_info, dir_path in directories_to_check:
                            if dir_path in line:
                                dir_info.has_permission_error = True

        except Exception as e:
            logger.debug(f"Batch Borg directory check failed: {e}")
            # Fallback to individual checks if batch fails
            for dir_info, dir_path in directories_to_check:
                try:
                    is_repo, repo_perm_error = await self._is_borg_repository(dir_path)
                    is_cache, cache_perm_error = await self._is_borg_cache(dir_path)
                    dir_info.is_borg_repo = is_repo
                    dir_info.is_borg_cache = is_cache
                    dir_info.has_permission_error = repo_perm_error or cache_perm_error
                except Exception:
                    continue

    def _mark_directory_as_borg_repo(
        self, directories_to_check: List[Tuple[DirectoryInfo, str]], target_path: str
    ) -> None:
        """Mark a directory as a Borg repository."""
        for dir_info, dir_path in directories_to_check:
            if dir_path == target_path:
                dir_info.is_borg_repo = True
                break

    def _mark_directory_as_borg_cache(
        self, directories_to_check: List[Tuple[DirectoryInfo, str]], target_path: str
    ) -> None:
        """Mark a directory as a Borg cache."""
        for dir_info, dir_path in directories_to_check:
            if dir_path == target_path:
                dir_info.is_borg_cache = True
                break

    async def _is_borg_repository(self, directory_path: str) -> tuple[bool, bool]:
        """
        Check if a directory is a Borg repository by looking for a config file with [repository] section.

        Returns:
            tuple[bool, bool]: (is_borg_repo, has_permission_error)
        """
        try:
            config_path = directory_path.rstrip("/") + "/config"

            # Use ls -la to get detailed information about the config file
            result = await self.command_executor.execute_command(
                command=["ls", "-la", config_path], timeout=5.0
            )

            if not result.success:
                if "Permission denied" in result.stderr:
                    logger.debug(
                        f"Permission denied accessing config file at {config_path}"
                    )
                    return False, True  # Not a repo, but has permission error
                return False, False

            # Check if it's actually a file (not a directory)
            if not result.stdout.startswith("-"):
                logger.debug(
                    f"Config path {config_path} exists but is not a regular file"
                )
                return False, False

            # Try to read config file content
            result = await self.command_executor.execute_command(
                command=["cat", config_path], timeout=10.0
            )

            if not result.success:
                if "Permission denied" in result.stderr:
                    logger.debug(
                        f"Permission denied reading config file at {config_path}"
                    )
                    return False, True  # Not a repo, but has permission error
                else:
                    logger.debug(
                        f"Failed to read config file at {config_path}: {result.stderr}"
                    )
                return False, False

            config_content = result.stdout
            is_repo = "[repository]" in config_content
            return is_repo, False

        except Exception as e:
            logger.debug(f"Error checking if {directory_path} is borg repository: {e}")
            return False, False

    async def _is_borg_cache(self, directory_path: str) -> tuple[bool, bool]:
        """
        Check if a directory is a Borg cache by looking for a config file with [cache] section.

        Returns:
            tuple[bool, bool]: (is_borg_cache, has_permission_error)
        """
        try:
            config_path = directory_path.rstrip("/") + "/config"

            # Use ls -la to get detailed information about the config file
            result = await self.command_executor.execute_command(
                command=["ls", "-la", config_path], timeout=5.0
            )

            if not result.success:
                if "Permission denied" in result.stderr:
                    logger.debug(
                        f"Permission denied accessing config file at {config_path}"
                    )
                    return False, True
                return False, False

            # Check if it's actually a file (not a directory)
            if not result.stdout.startswith("-"):
                logger.debug(
                    f"Config path {config_path} exists but is not a regular file"
                )
                return False, False

            # Try to read config file content
            result = await self.command_executor.execute_command(
                command=["cat", config_path], timeout=10.0
            )

            if not result.success:
                if "Permission denied" in result.stderr:
                    logger.debug(
                        f"Permission denied reading config file at {config_path}"
                    )
                    return False, True  # Not a cache, but has permission error
                else:
                    logger.debug(
                        f"Failed to read config file at {config_path}: {result.stderr}"
                    )
                return False, False

            config_content = result.stdout
            is_cache = "[cache]" in config_content
            return is_cache, False

        except Exception as e:
            logger.debug(f"Error checking if {directory_path} is borg cache: {e}")
            return False, False

    async def test_connectivity(self) -> bool:
        """
        Test if the command executor connectivity is working.

        Returns:
            True if command execution is accessible and working
        """
        try:
            result = await self.command_executor.execute_command(
                ["echo", "test"], timeout=5.0
            )
            return result.success and result.stdout.strip() == "test"
        except Exception as e:
            logger.debug(f"Connectivity test failed: {e}")
            return False
