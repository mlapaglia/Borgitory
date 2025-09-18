"""
ArchiveManager - Handles Borg archive operations and content management
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator, Any, cast

from borgitory.models.database import Repository
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.borg_command_builder import BorgCommandBuilder
from borgitory.utils.security import validate_archive_name, sanitize_path

logger = logging.getLogger(__name__)


class ArchiveManager:
    """
    Handles Borg archive operations and content management.

    Responsibilities:
    - List and query archive contents
    - Extract files from archives
    - Filter and organize archive content listings
    - Stream file content from archives
    - Manage archive metadata and structure
    """

    def __init__(
        self,
        job_executor: Optional[JobExecutor] = None,
        command_builder: Optional[BorgCommandBuilder] = None,
    ) -> None:
        self.job_executor = job_executor or JobExecutor()
        self.command_builder = command_builder or BorgCommandBuilder()

    async def list_archive_contents(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, Any]]:
        """List contents of a specific archive"""
        try:
            command, env = self.command_builder.build_list_archive_contents_command(
                repository, archive_name
            )
        except Exception as e:
            raise Exception(f"Command building failed: {str(e)}")

        try:
            # Use JobExecutor directly for simple synchronous operations
            process = await self.job_executor.start_process(command, env)
            result = await self.job_executor.monitor_process_output(process)

            if result.return_code == 0:
                # Parse JSON lines output from stdout
                output_text = result.stdout.decode("utf-8", errors="replace")
                contents = []

                for line in output_text.split("\n"):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            item = json.loads(line)
                            contents.append(item)
                        except json.JSONDecodeError:
                            continue

                return contents
            else:
                error_text = (
                    result.stderr.decode("utf-8", errors="replace")
                    if result.stderr
                    else "Unknown error"
                )
                raise Exception(
                    f"Borg list failed with code {result.return_code}: {error_text}"
                )

        except Exception as e:
            raise Exception(f"Failed to list archive contents: {str(e)}")

    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[Dict[str, Any]]:
        """List contents of a specific directory within an archive using FUSE mount"""
        logger.info(
            f"Listing directory '{path}' in archive '{archive_name}' of repository '{repository.name}' using FUSE mount"
        )

        from borgitory.services.archives.archive_mount_manager import (
            get_archive_mount_manager,
        )

        mount_manager = get_archive_mount_manager()

        # Mount the archive if not already mounted
        await mount_manager.mount_archive(repository, archive_name)

        # List the directory contents using filesystem operations
        contents = mount_manager.list_directory(repository, archive_name, path)

        logger.info(
            f"Listed {len(contents)} items from mounted archive {archive_name} path '{path}'"
        )
        return contents

    def _filter_directory_contents(
        self, all_entries: List[Dict[str, Any]], target_path: str = ""
    ) -> List[Dict[str, Any]]:
        """Filter entries to show only immediate children of target_path"""
        target_path = target_path.strip().strip("/")

        logger.info(
            f"Filtering {len(all_entries)} entries for target_path: '{target_path}'"
        )

        # Group entries by their immediate parent under target_path
        children = {}

        for entry in all_entries:
            entry_path = entry.get("path", "").lstrip("/")

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
                is_directory = len(path_parts) > 1 or entry.get("type") == "d"

                children[immediate_child] = {
                    "path": full_path,
                    "name": immediate_child,
                    "type": "d" if is_directory else entry.get("type", "f"),
                    "size": 0 if is_directory else entry.get("size", 0),
                    "mtime": entry.get("mtime"),
                    "mode": entry.get("mode"),
                    "uid": entry.get("uid"),
                    "gid": entry.get("gid"),
                    "healthy": entry.get("healthy", True),
                    "isdir": is_directory,
                    "children_count": 0 if not is_directory else None,
                }
            else:
                # This is another item in the same directory, possibly update info
                existing = children[immediate_child]
                if existing["type"] == "d":
                    # It's a directory, we might want to count children
                    if existing["children_count"] is not None:
                        existing["children_count"] += 1

        result = list(children.values())

        # Sort results: directories first, then files, both alphabetically
        result.sort(key=lambda x: (x["type"] != "d", x["name"].lower()))

        logger.info(f"Filtered to {len(result)} immediate children")
        return result

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ) -> AsyncGenerator[bytes, None]:
        """Extract a single file from an archive and stream it as an async generator"""
        try:
            command, env = self.command_builder.build_extract_command(
                repository, archive_name, file_path, extract_to_stdout=True
            )
        except Exception as e:
            raise Exception(f"Command building failed: {str(e)}")

        logger.info(f"Extracting file {file_path} from archive {archive_name}")

        # Start the borg process
        process = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            while True:
                # Read chunk from Borg process - this already yields control to event loop
                if not process.stdout:
                    break
                chunk = await process.stdout.read(65536)  # 64KB chunks for efficiency
                if not chunk:
                    break

                # Yield chunk to client
                yield chunk

            # Wait for the process to complete and check for errors
            return_code = await process.wait()
            if return_code != 0:
                # Read any error messages
                stderr_data = await process.stderr.read() if process.stderr else b""
                error_msg = stderr_data.decode("utf-8", errors="replace")
                raise Exception(
                    f"Borg extract failed with code {return_code}: {error_msg}"
                )

        except Exception as e:
            # Ensure the process is terminated
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise Exception(f"File extraction failed: {str(e)}")

    async def get_archive_metadata(
        self, repository: Repository, archive_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific archive"""
        try:
            # Get repository info which includes archive information
            command, env = self.command_builder.build_repo_info_command(repository)

            # Use JobExecutor for consistent execution
            process = await self.job_executor.start_process(command, env)
            result = await self.job_executor.monitor_process_output(process)

            if result.return_code == 0:
                output_text = result.stdout.decode("utf-8", errors="replace")
                try:
                    repo_info = json.loads(output_text)
                    archives = repo_info.get("archives", [])

                    # Find the specific archive
                    for archive in archives:
                        if archive.get("name") == archive_name:
                            return cast(Dict[str, Any], archive)

                    return None  # Archive not found
                except json.JSONDecodeError:
                    logger.warning("Could not parse repository info JSON")
                    return None
            else:
                error_text = (
                    result.stderr.decode("utf-8", errors="replace")
                    if result.stderr
                    else "Unknown error"
                )
                logger.error(f"Failed to get repository info: {error_text}")
                return None

        except Exception as e:
            logger.error(f"Error getting archive metadata: {e}")
            return None

    def calculate_directory_size(
        self, entries: List[Dict[str, Any]], directory_path: str = ""
    ) -> int:
        """Calculate the total size of all files in a directory path"""
        total_size = 0
        directory_path = directory_path.strip().strip("/")

        for entry in entries:
            entry_path = entry.get("path", "").lstrip("/")

            # Check if this entry is within the target directory
            if directory_path:
                if (
                    not entry_path.startswith(directory_path + "/")
                    and entry_path != directory_path
                ):
                    continue

            # Add size if it's a file (not a directory)
            if entry.get("type") != "d":
                total_size += entry.get("size", 0)

        return total_size

    def find_entries_by_pattern(
        self, entries: List[Dict[str, Any]], pattern: str, case_sensitive: bool = False
    ) -> List[Dict[str, Any]]:
        """Find archive entries matching a pattern"""
        import re

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            # If pattern is not a valid regex, treat it as a literal string
            pattern = re.escape(pattern)
            regex = re.compile(pattern, flags)

        matching_entries = []
        for entry in entries:
            path = entry.get("path", "")
            name = entry.get("name", path.split("/")[-1] if path else "")

            if regex.search(path) or regex.search(name):
                matching_entries.append(entry)

        return matching_entries

    def get_file_type_summary(self, entries: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get a summary of file types in the archive"""
        type_counts: Dict[str, int] = {}

        for entry in entries:
            if entry.get("type") == "d":
                entry_type = "directory"
            else:
                path = entry.get("path", "")
                if "." in path:
                    extension = path.split(".")[-1].lower()
                    entry_type = f".{extension}"
                else:
                    entry_type = "no extension"

            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        return dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True))

    def validate_archive_path(
        self, archive_name: str, file_path: str
    ) -> Dict[str, str]:
        """Validate archive name and file path parameters"""
        errors = {}

        try:
            validate_archive_name(archive_name)
        except Exception as e:
            errors["archive_name"] = str(e)

        try:
            sanitize_path(file_path)
        except Exception as e:
            errors["file_path"] = str(e)

        return errors
