"""
ArchiveManager - Handles Borg archive operations and content management
"""

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Dict, List, Optional, AsyncGenerator, TypedDict, TYPE_CHECKING

from borgitory.models.database import Repository
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.utils.security import (
    cleanup_temp_keyfile,
    validate_archive_name,
    sanitize_path,
    secure_borg_command,
)

if TYPE_CHECKING:
    from borgitory.services.archives.archive_mount_manager import ArchiveMountManager

logger = logging.getLogger(__name__)


@dataclass
class ArchiveEntry:
    """Individual archive entry (file/directory) structure"""

    # Required fields
    path: str
    name: str
    type: str  # 'f' for file, 'd' for directory, etc.
    size: int
    isdir: bool

    # Optional fields from Borg JSON output
    mtime: Optional[str] = None
    mode: Optional[str] = None
    uid: Optional[int] = None
    gid: Optional[int] = None
    healthy: Optional[bool] = None

    # Additional computed fields
    children_count: Optional[int] = None


class ArchiveMetadata(TypedDict, total=False):
    """Archive metadata structure from Borg repository info"""

    # Standard Borg archive fields
    name: str
    id: str
    start: str
    end: str
    duration: float
    stats: Dict[str, object]
    # Size field that may be present in some Borg versions
    size: int
    # Additional fields that may be present
    command_line: List[str]
    hostname: str
    username: str
    comment: str


class FileTypeSummary(TypedDict):
    """File type summary structure"""

    # Key is file type (extension or 'directory'), value is count
    # This is a regular dict with string keys and int values


class ArchiveValidationResult(TypedDict):
    """Archive path validation result structure"""

    # Key is field name, value is error message (empty dict if no errors)


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
        job_executor: JobExecutor,
        mount_manager: "ArchiveMountManager",
    ) -> None:
        self.job_executor = job_executor
        self.mount_manager = mount_manager

    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[ArchiveEntry]:
        """List contents of a specific directory within an archive using FUSE mount"""
        logger.info(
            f"Listing directory '{path}' in archive '{archive_name}' of repository '{repository.name}' using FUSE mount"
        )

        mount_manager = self.mount_manager

        # Mount the archive if not already mounted
        await mount_manager.mount_archive(repository, archive_name)

        # List the directory contents using filesystem operations
        contents = mount_manager.list_directory(repository, archive_name, path)

        logger.info(
            f"Listed {len(contents)} items from mounted archive {archive_name} path '{path}'"
        )
        return contents

    def _filter_directory_contents(
        self, all_entries: List[ArchiveEntry], target_path: str = ""
    ) -> List[ArchiveEntry]:
        """Filter entries to show only immediate children of target_path"""
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

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ) -> AsyncGenerator[bytes, None]:
        """Extract a single file from an archive and stream it as an async generator"""
        logger.info(f"Extracting file {file_path} from archive {archive_name}")

        # Build the Borg extract command
        base_command = "borg extract"
        additional_args = ["--stdout", f"{repository.path}::{archive_name}", file_path]

        keyfile_content = repository.get_keyfile_content()
        passphrase = repository.get_passphrase() or ""

        async with secure_borg_command(
            base_command=base_command,
            repository_path="",  # Already included in additional_args
            passphrase=passphrase,
            keyfile_content=keyfile_content,
            additional_args=additional_args,
            cleanup_keyfile=False,
        ) as (final_command, env, temp_keyfile_path):
            try:
                process = await asyncio.create_subprocess_exec(
                    *final_command,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    while True:
                        if not process.stdout:
                            break
                        chunk = await process.stdout.read(
                            65536
                        )  # 64KB chunks for efficiency
                        if not chunk:
                            break

                        yield chunk

                    return_code = await process.wait()
                    if return_code != 0:
                        stderr_data = (
                            await process.stderr.read() if process.stderr else b""
                        )
                        error_msg = stderr_data.decode("utf-8", errors="replace")
                        raise Exception(
                            f"Borg extract failed with code {return_code}: {error_msg}"
                        )

                except Exception as e:
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                    raise Exception(f"File extraction failed: {str(e)}")
            finally:
                # Always cleanup the temporary keyfile
                if temp_keyfile_path:
                    cleanup_temp_keyfile(temp_keyfile_path)

    async def get_archive_metadata(
        self, repository: Repository, archive_name: str
    ) -> Optional[ArchiveMetadata]:
        """Get metadata for a specific archive"""
        try:
            base_command = "borg info"
            additional_args = ["--json", repository.path]
            keyfile_content = repository.get_keyfile_content()
            passphrase = repository.get_passphrase() or ""

            async with secure_borg_command(
                base_command=base_command,
                repository_path="",  # Already included in additional_args
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=additional_args,
            ) as (final_command, env, temp_keyfile_path):
                process = await self.job_executor.start_process(final_command, env)
                result = await self.job_executor.monitor_process_output(process)

                if result.return_code == 0:
                    output_text = result.stdout.decode("utf-8", errors="replace")
                    try:
                        repo_info = json.loads(output_text)
                        archives = repo_info.get("archives", [])

                        # Find the specific archive
                        for archive in archives:
                            if archive.get("name") == archive_name:
                                # Convert to ArchiveMetadata TypedDict
                                metadata: ArchiveMetadata = {}
                                if archive.get("name"):
                                    metadata["name"] = archive["name"]
                                if archive.get("id"):
                                    metadata["id"] = archive["id"]
                                if archive.get("start"):
                                    metadata["start"] = archive["start"]
                                if archive.get("end"):
                                    metadata["end"] = archive["end"]
                                if archive.get("duration"):
                                    metadata["duration"] = archive["duration"]
                                if archive.get("stats"):
                                    metadata["stats"] = archive["stats"]
                                if archive.get("size"):
                                    metadata["size"] = archive["size"]
                                if archive.get("command_line"):
                                    metadata["command_line"] = archive["command_line"]
                                if archive.get("hostname"):
                                    metadata["hostname"] = archive["hostname"]
                                if archive.get("username"):
                                    metadata["username"] = archive["username"]
                                if archive.get("comment"):
                                    metadata["comment"] = archive["comment"]
                                return metadata

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
        self, entries: List[ArchiveEntry], directory_path: str = ""
    ) -> int:
        """Calculate the total size of all files in a directory path"""
        total_size = 0
        directory_path = directory_path.strip().strip("/")

        for entry in entries:
            entry_path = entry.path.lstrip("/")

            # Check if this entry is within the target directory
            if directory_path:
                if (
                    not entry_path.startswith(directory_path + "/")
                    and entry_path != directory_path
                ):
                    continue

            # Add size if it's a file (not a directory)
            if entry.type != "d":
                total_size += entry.size

        return total_size

    def find_entries_by_pattern(
        self, entries: List[ArchiveEntry], pattern: str, case_sensitive: bool = False
    ) -> List[ArchiveEntry]:
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
            path = entry.path
            name = entry.name

            if regex.search(path) or regex.search(name):
                matching_entries.append(entry)

        return matching_entries

    def get_file_type_summary(self, entries: List[ArchiveEntry]) -> Dict[str, int]:
        """Get a summary of file types in the archive"""
        type_counts: Dict[str, int] = {}

        for entry in entries:
            if entry.type == "d":
                entry_type = "directory"
            else:
                path = entry.path
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
