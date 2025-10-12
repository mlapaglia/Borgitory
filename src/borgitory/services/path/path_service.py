"""
Unified path service implementation.

This service provides filesystem operations that work across different
environments by using the appropriate CommandExecutorProtocol implementation.
"""

import logging
import posixpath
from typing import List, Tuple

from borgitory.models.borg_info import BorgDefaultDirectories
from borgitory.protocols.path_protocols import (
    PathServiceInterface,
)
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.command_protocols import CommandResult
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
        command_executor: CommandExecutorProtocol,
    ):
        self.command_executor = command_executor

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
            # Store directory flag for sorting
            dir_info._is_directory = is_directory
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
                not getattr(x, "_is_directory", False),
                x.name.lower(),
            )
        )

        return items

    async def _batch_check_borg_directories(
        self, directories_to_check: List[Tuple[DirectoryInfo, str]]
    ) -> None:
        """
        Batch check multiple directories for Borg repository/cache indicators.

        Args:
            directories_to_check: List of (DirectoryInfo, path) tuples to check
        """
        if not directories_to_check:
            return

        # Build a single command that checks all directories at once
        # Use find to locate config files and grep to check their content
        paths = [path for _, path in directories_to_check]

        # Step 1: Find all config files in the target directories
        find_cmd = (
            ["find"] + paths + ["-maxdepth", "1", "-name", "config", "-type", "f"]
        )

        try:
            logger.info(f"Finding config files with command: {find_cmd}")
            find_result = await self.command_executor.execute_command(
                find_cmd, timeout=10.0
            )

            if not find_result.stdout.strip():
                logger.info("No config files found")
                return

            if not find_result.success:
                logger.info(
                    f"Find command had errors but may have found some files: {find_result.stderr}"
                )

            config_files = [
                f.strip() for f in find_result.stdout.strip().split("\n") if f.strip()
            ]
            logger.info(f"Found {len(config_files)} config files: {config_files}")

            if not config_files:
                return

            repo_cmd = ["grep", "-l", "^\\[repository\\]"] + config_files
            repo_result = await self.command_executor.execute_command(
                repo_cmd, timeout=5.0
            )

            cache_cmd = ["grep", "-l", "^\\[cache\\]"] + config_files
            cache_result = await self.command_executor.execute_command(
                cache_cmd, timeout=5.0
            )

            # Combine results
            all_results = []

            if repo_result.success and repo_result.stdout.strip():
                for config_file in repo_result.stdout.strip().split("\n"):
                    if config_file.strip():
                        all_results.append(f"REPO:{config_file.strip()}")

            if cache_result.success and cache_result.stdout.strip():
                for config_file in cache_result.stdout.strip().split("\n"):
                    if config_file.strip():
                        all_results.append(f"CACHE:{config_file.strip()}")

            logger.info(f"Batch check found {len(all_results)} results: {all_results}")

            # Create result object for existing parsing logic
            result = CommandResult(
                success=True,
                return_code=0,
                stdout="\n".join(all_results),
                stderr="",
                duration=0.0,
            )

        except Exception as e:
            logger.debug(f"Directory query failed: {e}")
            raise e

        if result.success and result.stdout:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                if line.startswith("REPO:"):
                    config_path = line[5:]  # Remove "REPO:" prefix
                    dir_path = config_path.rsplit("/", 1)[0]
                    self._mark_directory_as_borg_repo(directories_to_check, dir_path)
                elif line.startswith("CACHE:"):
                    config_path = line[6:]  # Remove "CACHE:" prefix
                    dir_path = config_path.rsplit("/", 1)[0]
                    self._mark_directory_as_borg_cache(directories_to_check, dir_path)

        # For directories that weren't processed (no output), assume they have permission errors
        processed_dirs = set()
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.startswith(("REPO:", "CACHE:")):
                    config_path = line.split(":", 1)[1]
                    dir_path = config_path.rsplit("/", 1)[0]
                    processed_dirs.add(dir_path)

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

    async def get_default_directories(self) -> BorgDefaultDirectories:
        """
        Determine Borg's default directories based on environment variable resolution.

        Uses command executor to query environment variables from the actual execution
        environment (e.g., WSL when running on Windows but executing in Linux).

        Follows Borg's environment variable precedence rules:
        - BORG_BASE_DIR defaults to $HOME or ~$USER or ~
        - BORG_CACHE_DIR defaults to $BORG_BASE_DIR/.cache/borg (or $XDG_CACHE_HOME/borg if XDG is set)
        - BORG_CONFIG_DIR defaults to $BORG_BASE_DIR/.config/borg (or $XDG_CONFIG_HOME/borg if XDG is set)
        - BORG_SECURITY_DIR defaults to $BORG_CONFIG_DIR/security
        - BORG_KEYS_DIR defaults to $BORG_CONFIG_DIR/keys
        """

        result = await self.command_executor.execute_command(
            [
                "sh",
                "-c",
                "printf 'BORG_BASE_DIR=%s\\n' \"$BORG_BASE_DIR\"; "
                "printf 'HOME=%s\\n' \"$HOME\"; "
                "printf 'XDG_CACHE_HOME=%s\\n' \"$XDG_CACHE_HOME\"; "
                "printf 'XDG_CONFIG_HOME=%s\\n' \"$XDG_CONFIG_HOME\"; "
                "printf 'TMPDIR=%s\\n' \"${TMPDIR:-/tmp}\"; "
                "printf 'HOME_FROM_CD=%s\\n' \"$(cd ~ 2>/dev/null && pwd || echo)\"",
            ]
        )

        if not result.success:
            logger.warning(f"Failed to get environment variables: {result.error}")
            return BorgDefaultDirectories(
                base_dir="",
                cache_dir="",
                config_dir="",
                security_dir="",
                keys_dir="",
                temp_dir="/tmp",
            )

        env_vars = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value

        borg_base_dir_explicit = env_vars.get("BORG_BASE_DIR", "")
        home = env_vars.get("HOME", "")
        xdg_cache_home = env_vars.get("XDG_CACHE_HOME", "")
        xdg_config_home = env_vars.get("XDG_CONFIG_HOME", "")
        temp_dir = env_vars.get("TMPDIR", "/tmp") or "/tmp"
        home_from_cd = env_vars.get("HOME_FROM_CD", "")

        if borg_base_dir_explicit:
            base_dir = borg_base_dir_explicit
        else:
            if not home and home_from_cd:
                home = home_from_cd
            base_dir = home

        if not borg_base_dir_explicit and xdg_cache_home:
            cache_dir = self.secure_join(xdg_cache_home, "borg")
        else:
            cache_dir = self.secure_join(base_dir, ".cache", "borg")

        if not borg_base_dir_explicit and xdg_config_home:
            config_dir = self.secure_join(xdg_config_home, "borg")
        else:
            config_dir = self.secure_join(base_dir, ".config", "borg")

        security_dir = self.secure_join(config_dir, "security")
        keys_dir = self.secure_join(config_dir, "keys")

        return BorgDefaultDirectories(
            base_dir=base_dir,
            cache_dir=cache_dir,
            config_dir=config_dir,
            security_dir=security_dir,
            keys_dir=keys_dir,
            temp_dir=temp_dir,
        )
