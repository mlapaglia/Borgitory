"""
Borg List Archive Manager - Uses borg list command for archive browsing
"""

import asyncio
import json
import logging
import os
from pathlib import PurePath
from typing import List, AsyncGenerator, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timedelta

from starlette.responses import StreamingResponse

from borgitory.models.database import Repository
from borgitory.services.archives.archive_models import ArchiveEntry
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.utils.security import (
    build_secure_borg_command_with_keyfile,
    secure_borg_command,
    validate_archive_name,
)

if TYPE_CHECKING:
    from borgitory.protocols.command_protocols import ProcessExecutorProtocol

logger = logging.getLogger(__name__)


class ArchiveManager:
    """
    Archive manager implementation that uses borg list command instead of FUSE mounting.

    This approach:
    - Avoids the complexity of FUSE mounting
    - Works reliably across different platforms
    - Uses direct borg commands for better performance
    - Provides the same interface as the mount-based manager
    - Caches archive contents in memory for improved performance
    """

    def __init__(
        self,
        job_executor: "ProcessExecutorProtocol",
        command_executor: CommandExecutorProtocol,
        cache_ttl: timedelta = timedelta(minutes=30),
    ) -> None:
        self.job_executor = job_executor
        self.command_executor = command_executor
        self.cache_ttl = cache_ttl

        # In-memory cache for archive contents
        # Key: "repository_path::archive_name", Value: (items, cached_at)
        self._archive_cache: Dict[str, tuple[List[ArchiveEntry], datetime]] = {}

    def _get_cache_key(self, repository: Repository, archive_name: str) -> str:
        """Generate cache key for repository and archive combination"""
        return f"{repository.path}::{archive_name}"

    def _is_cache_valid(self, cached_at: datetime) -> bool:
        """Check if cached data is still valid based on TTL"""
        return datetime.now() - cached_at < self.cache_ttl

    def _get_cached_items(
        self, repository: Repository, archive_name: str
    ) -> Optional[List[ArchiveEntry]]:
        """Get cached archive items if available and valid"""
        cache_key = self._get_cache_key(repository, archive_name)

        if cache_key in self._archive_cache:
            items, cached_at = self._archive_cache[cache_key]
            if self._is_cache_valid(cached_at):
                logger.info(f"Cache hit for {cache_key}")
                return items
            else:
                logger.info(f"Cache expired for {cache_key}")
                # Remove expired entry
                del self._archive_cache[cache_key]

        return None

    def _cache_items(
        self, repository: Repository, archive_name: str, items: List[ArchiveEntry]
    ) -> None:
        """Cache archive items with current timestamp"""
        cache_key = self._get_cache_key(repository, archive_name)
        self._archive_cache[cache_key] = (items, datetime.now())
        logger.info(f"Cached {len(items)} items for {cache_key}")

    def clear_cache(
        self,
        repository: Optional[Repository] = None,
        archive_name: Optional[str] = None,
    ) -> None:
        """
        Clear cache entries.

        Args:
            repository: If provided, only clear cache for this repository
            archive_name: If provided with repository, only clear cache for this specific archive
        """
        if repository is None:
            # Clear all cache
            self._archive_cache.clear()
            logger.info("Cleared all archive cache")
        elif archive_name is None:
            # Clear cache for all archives in this repository
            repo_path = repository.path
            keys_to_remove = [
                key
                for key in self._archive_cache.keys()
                if key.startswith(f"{repo_path}::")
            ]
            for key in keys_to_remove:
                del self._archive_cache[key]
            logger.info(
                f"Cleared cache for repository {repo_path} ({len(keys_to_remove)} entries)"
            )
        else:
            # Clear cache for specific repository and archive
            cache_key = self._get_cache_key(repository, archive_name)
            if cache_key in self._archive_cache:
                del self._archive_cache[cache_key]
                logger.info(f"Cleared cache for {cache_key}")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        total_entries = len(self._archive_cache)
        valid_entries = sum(
            1
            for _, cached_at in self._archive_cache.values()
            if self._is_cache_valid(cached_at)
        )
        expired_entries = total_entries - valid_entries

        return {
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_ttl_minutes": int(self.cache_ttl.total_seconds() / 60),
        }

    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[ArchiveEntry]:
        """
        List contents of a specific directory within an archive using borg list command.

        This implementation:
        1. Checks cache first for the complete archive contents
        2. Uses borg list with JSON output to get all items if not cached
        3. Filters items to show only immediate children of the target path
        4. Groups items by their immediate parent directory
        5. Returns the same ArchiveEntry format as the mount-based implementation
        """
        logger.info(
            f"Listing directory '{path}' in archive '{archive_name}' of repository '{repository.name}' using borg list"
        )

        # Clean and normalize the path
        clean_path = path.strip().strip("/")

        try:
            # Try to get cached items first
            all_items = self._get_cached_items(repository, archive_name)

            if all_items is None:
                # Cache miss - get all items from the archive using borg list
                logger.info(
                    f"Cache miss for {repository.path}::{archive_name}, fetching from borg"
                )
                all_items = await self._get_archive_items(repository, archive_name)

                # Cache the results
                self._cache_items(repository, archive_name, all_items)
            else:
                logger.info(f"Cache hit for {repository.path}::{archive_name}")

            # Filter to show only immediate children of the target path
            filtered_items = self._filter_directory_contents(all_items, clean_path)

            logger.info(
                f"Listed {len(filtered_items)} items from archive {archive_name} path '{path}'"
            )
            return filtered_items

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            raise Exception(f"Failed to list directory: {str(e)}")

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ) -> StreamingResponse:
        """Extract a single file from an archive and stream it to the client"""
        result = None
        try:
            # Validate inputs
            if not archive_name or not archive_name.strip():
                raise ValueError("Archive name must be a non-empty string")

            if not file_path:
                raise ValueError("File path is required")

            validate_archive_name(archive_name)

            # Build borg extract command with --stdout
            # Ensure file_path starts with / for borg
            if not file_path.startswith("/"):
                file_path = "/" + file_path
            borg_args = ["--stdout", f"{repository.path}::{archive_name}", file_path]

            # Use manual keyfile management for streaming operations
            result = build_secure_borg_command_with_keyfile(
                base_command="borg extract",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=borg_args,
            )
            command, env = result.command, result.environment

            logger.info(f"Extracting file {file_path} from archive {archive_name}")

            # Start the borg process using command executor for cross-platform compatibility
            process = await self.command_executor.create_subprocess(
                command=command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def generate_stream() -> AsyncGenerator[bytes, None]:
                """Generator function to stream the file content with automatic backpressure"""
                try:
                    while True:
                        if process.stdout is None:
                            break
                        chunk = await process.stdout.read(
                            65536
                        )  # 64KB chunks for efficiency
                        if not chunk:
                            break

                        yield chunk

                    # Wait for process to complete
                    return_code = await process.wait()

                    # Check for errors after process completes
                    if return_code != 0:
                        # Read stderr for error details
                        stderr_data = b""
                        if process.stderr:
                            try:
                                stderr_data = await process.stderr.read()
                            except Exception as e:
                                logger.warning(f"Could not read stderr: {e}")

                        error_msg = (
                            stderr_data.decode("utf-8", errors="replace")
                            if stderr_data
                            else "Unknown error"
                        )
                        logger.error(
                            f"Borg extract process failed with code {return_code}: {error_msg}"
                        )
                        raise Exception(
                            f"Borg extract failed with code {return_code}: {error_msg}"
                        )

                except Exception:
                    # Clean up process if still running
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                    raise
                finally:
                    # Clean up keyfile after streaming completes
                    result.cleanup_temp_files()

            filename = os.path.basename(file_path)

            return StreamingResponse(
                generate_stream(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            # Clean up keyfile if error occurs before streaming starts
            if result:
                result.cleanup_temp_files()
            logger.error(f"Failed to extract file {file_path}: {str(e)}")
            raise Exception(f"Failed to extract file: {str(e)}")

    async def _get_archive_items(
        self, repository: Repository, archive_name: str
    ) -> List[ArchiveEntry]:
        """
        Get all items from an archive using borg list command with JSON output.

        Returns a flat list of all ArchiveEntry objects in the archive.
        """
        # Build the borg list command with JSON output
        base_command = "borg list"
        additional_args = [
            "--json-lines",
            "--format",
            json.dumps(
                {
                    "type": "{type}",
                    "mode": "{mode}",
                    "uid": "{uid}",
                    "gid": "{gid}",
                    "user": "{user}",
                    "group": "{group}",
                    "size": "{size}",
                    "mtime": "{mtime}",
                    "path": "{path}",
                }
            ),
            f"{repository.path}::{archive_name}",
        ]

        keyfile_content = repository.get_keyfile_content()
        passphrase = repository.get_passphrase() or ""

        async with secure_borg_command(
            base_command=base_command,
            repository_path="",  # Already included in additional_args
            passphrase=passphrase,
            keyfile_content=keyfile_content,
            additional_args=additional_args,
        ) as (final_command, env, temp_keyfile_path):
            try:
                # Use command_executor directly instead of job_executor to avoid WSL FIFO issues
                cmd_result = await self.command_executor.execute_command(
                    command=final_command,
                    env=env,
                    timeout=60.0,  # 1 minute timeout for listing
                )

                if not cmd_result.success:
                    error_text = (
                        cmd_result.stderr or cmd_result.error or "Unknown error"
                    )
                    raise Exception(f"Borg list failed: {error_text}")

                # Parse the JSON lines output
                items = self._parse_borg_list_output(cmd_result.stdout)

                logger.info(f"Retrieved {len(items)} items from archive {archive_name}")
                return items

            except Exception as e:
                logger.error(f"Error getting archive items: {e}")
                raise

    def _parse_borg_list_output(self, output_text: str) -> List[ArchiveEntry]:
        """
        Parse the JSON lines output from borg list command.

        Converts the JSON output into ArchiveEntry objects.
        """
        items = []
        lines = output_text.strip().split("\n")

        for line in lines:
            if not line.strip():
                continue

            try:
                data = json.loads(line)

                # Parse item type
                type_char = data.get("type", "-")
                if type_char == "d":
                    item_type = "d"  # directory
                elif type_char == "-":
                    item_type = "f"  # file
                elif type_char == "l":
                    item_type = "l"  # symlink
                else:
                    item_type = "f"  # default to file for other types

                # Parse mtime
                mtime = None
                if data.get("mtime"):
                    try:
                        # Convert ISO format to string
                        mtime = data["mtime"]
                    except (ValueError, TypeError):
                        pass

                # Extract name from path
                path = data.get("path", "")
                name = PurePath(path).name if path else ""

                # Parse size
                try:
                    size = int(data.get("size", 0))
                except (ValueError, TypeError):
                    size = 0

                # Determine if it's a directory
                is_directory = item_type == "d"

                # Extract mode (permissions)
                mode = data.get("mode", "")
                if mode and len(mode) >= 4:
                    # Extract user permissions (e.g., "rwx" from "drwxr-xr-x")
                    user_mode = (
                        mode[1:4] if mode.startswith(("d", "-", "l")) else mode[:3]
                    )
                else:
                    user_mode = None

                entry = ArchiveEntry(
                    path=path,
                    name=name,
                    type=item_type,
                    size=size,
                    isdir=is_directory,
                    mtime=mtime,
                    mode=user_mode,
                    uid=int(data.get("uid", 0))
                    if data.get("uid") is not None
                    else None,
                    gid=int(data.get("gid", 0))
                    if data.get("gid") is not None
                    else None,
                    healthy=True,  # Assume healthy unless we have evidence otherwise
                )

                items.append(entry)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(
                    f"Failed to parse borg list line: {line[:100]}... Error: {e}"
                )
                continue

        return items

    def _filter_directory_contents(
        self, all_entries: List[ArchiveEntry], target_path: str = ""
    ) -> List[ArchiveEntry]:
        """
        Filter entries to show only immediate children of target_path.

        This is the same logic as the original ArchiveManager but adapted
        for the borg list output format.
        """
        target_path = target_path.strip().strip("/")

        logger.info(
            f"Filtering {len(all_entries)} entries for target_path: '{target_path}'"
        )

        # Group entries by their immediate parent under target_path
        children: Dict[str, ArchiveEntry] = {}

        for entry in all_entries:
            entry_path = entry.path.lstrip("/")

            logger.debug(f"Processing entry path: '{entry_path}'")

            # Determine if this entry is a direct child of target_path
            if target_path:
                # For subdirectory like "data", we want entries like:
                # "data/file.txt" -> include as "file.txt"
                # "data/subdir/file.txt" -> include as "subdir" (directory)
                if not entry_path.startswith(target_path + "/"):
                    continue

                # Remove the target path prefix
                relative_path = entry_path[len(target_path) + 1 :]

            else:
                # For root directory, we want entries like:
                # "file.txt" -> include as "file.txt"
                # "data/file.txt" -> include as "data" (directory)
                relative_path = entry_path

            if not relative_path:
                continue

            # Get the first component (immediate child)
            path_parts = relative_path.split("/")
            immediate_child = path_parts[0]

            # Build full path for this item
            full_path = (
                f"{target_path}/{immediate_child}" if target_path else immediate_child
            )

            if immediate_child not in children:
                # Determine if this is a directory or file
                # Use the actual Borg entry type - 'd' means directory
                is_directory = len(path_parts) > 1 or entry.type == "d"

                archive_entry: ArchiveEntry = ArchiveEntry(
                    path=full_path,
                    name=immediate_child,
                    type="d" if is_directory else entry.type,
                    size=0 if is_directory else entry.size,
                    isdir=is_directory,
                    mtime=entry.mtime,
                    mode=entry.mode,
                    uid=entry.uid,
                    gid=entry.gid,
                    healthy=entry.healthy,
                    children_count=None if not is_directory else 0,
                )

                children[immediate_child] = archive_entry
            else:
                # This is another item in the same directory, possibly update info
                existing = children[immediate_child]
                if existing.type == "d":
                    # It's a directory, we might want to count children
                    current_count = existing.children_count
                    if isinstance(current_count, int):
                        existing.children_count = current_count + 1

        result = list(children.values())

        # Sort results: directories first, then files, both alphabetically
        result.sort(key=lambda x: (x.type != "d", x.name.lower()))

        logger.info(f"Filtered to {len(result)} immediate children")
        return result
