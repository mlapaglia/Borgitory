"""
Archive Mount Manager - FUSE-based archive browsing system
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING, TypedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.utils.datetime_utils import now_utc

from borgitory.models.database import Repository
from borgitory.utils.security import secure_borg_command, cleanup_temp_keyfile
from borgitory.services.archives.archive_manager import ArchiveEntry
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol

if TYPE_CHECKING:
    from borgitory.protocols.command_protocols import ProcessExecutorProtocol

logger = logging.getLogger(__name__)


class MountStatEntry(TypedDict):
    """Statistics for a single mount entry"""

    archive: str
    mount_point: str
    mounted_at: str
    last_accessed: str


class MountStatsResponse(TypedDict):
    """Response structure for mount statistics"""

    active_mounts: int
    mounts: List[MountStatEntry]


@dataclass
class MountInfo:
    """Information about a mounted archive"""

    repository_path: str
    archive_name: str
    mount_point: Path
    mounted_at: datetime
    last_accessed: datetime
    temp_keyfile_path: Optional[str] = None
    process: Optional[asyncio.subprocess.Process] = None


class ArchiveMountManager:
    """Manages FUSE mounts for Borg archives"""

    def __init__(
        self,
        job_executor: "ProcessExecutorProtocol",
        command_executor: CommandExecutorProtocol,
        path_config: "PathConfigurationService",
        mount_timeout: timedelta = timedelta(seconds=1800),
        mounting_timeout: timedelta = timedelta(seconds=30),
    ) -> None:
        self.path_config = path_config
        self.active_mounts: Dict[str, MountInfo] = {}  # key: repo_path::archive_name
        self.mount_timeout = mount_timeout
        self.mounting_timeout = mounting_timeout
        self.job_executor = job_executor
        self.command_executor = command_executor

        # Determine base mount directory based on platform
        self.base_mount_dir = self._get_base_mount_dir()

    def _get_base_mount_dir(self) -> Path:
        """Get the base mount directory based on platform configuration"""
        if self.path_config.is_windows():
            # Use WSL temp directory for Windows
            return Path("/tmp/borgitory/borgitory-mounts")
        else:
            # Use configured temp directory for Unix systems
            temp_base = self.path_config.get_base_temp_dir()
            return Path(f"{temp_base}/borgitory-mounts")

    def _get_mount_key(self, repository: Repository, archive_name: str) -> str:
        """Generate unique key for mount"""
        return f"{repository.path}::{archive_name}"

    def _get_mount_point(self, repository: Repository, archive_name: str) -> Path:
        """Generate mount point path"""
        safe_repo_name = repository.name.replace("/", "_").replace(" ", "_")
        safe_archive_name = archive_name.replace("/", "_").replace(" ", "_")
        return self.base_mount_dir / f"{safe_repo_name}_{safe_archive_name}"

    async def _ensure_base_mount_dir(self) -> None:
        """Ensure the base mount directory exists using the command executor"""
        # Use command executor to create directory in the appropriate environment
        await self.command_executor.execute_command(
            command=["mkdir", "-p", self.base_mount_dir.as_posix()], timeout=10.0
        )

    async def _ensure_mount_point_dir(self, mount_point: Path) -> None:
        """Ensure the specific mount point directory exists using the command executor"""
        # Use command executor to create directory in the appropriate environment
        await self.command_executor.execute_command(
            command=["mkdir", "-p", mount_point.as_posix()], timeout=10.0
        )

    async def _verify_mount_ready(self, mount_point: Path) -> bool:
        """Verify that the mount point is accessible and working"""
        try:
            # Try to list the directory contents
            result = await self.command_executor.execute_command(
                command=["ls", "-la", mount_point.as_posix()], timeout=10.0
            )
            return result.success
        except Exception as e:
            logger.warning(f"Could not verify mount readiness: {e}")
            return False

    async def mount_archive(self, repository: Repository, archive_name: str) -> Path:
        """Mount an archive and return the mount point"""
        await self._ensure_base_mount_dir()

        mount_key = self._get_mount_key(repository, archive_name)

        if mount_key in self.active_mounts:
            mount_info = self.active_mounts[mount_key]
            mount_info.last_accessed = now_utc()
            logger.info(f"Archive already mounted at {mount_info.mount_point}")
            return mount_info.mount_point

        mount_point = self._get_mount_point(repository, archive_name)

        try:
            await self._ensure_mount_point_dir(mount_point)

            logger.info(f"Mounting archive {archive_name} at {mount_point}")

            async with secure_borg_command(
                base_command="borg mount",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=[
                    f"{repository.path}::{archive_name}",
                    mount_point.as_posix(),
                    "-f",  # foreground mode for better process control
                ],
                cleanup_keyfile=False,
            ) as (command, env, temp_keyfile_path):
                # Check if we're using WSL - if so, use daemon mode to avoid RPC issues
                if self.command_executor.get_platform_name() == "wsl":
                    # For WSL, use daemon mode and regular command execution to avoid RPC handle issues
                    logger.info("Using WSL-compatible daemon mode mounting")

                    # Modify command to use daemon mode for WSL
                    daemon_command = command[:-1] + ["-d"]  # Replace -f with -d

                    result = await self.command_executor.execute_command(
                        command=daemon_command, env=env, timeout=30.0
                    )

                    if not result.success:
                        logger.error(
                            f"WSL mount command failed with return code: {result.return_code}"
                        )
                        logger.error(f"Mount stderr: {result.stderr}")
                        logger.error(f"Mount stdout: {result.stdout}")
                        raise Exception(
                            f"Mount failed: {result.stderr or result.stdout or 'Unknown error'}"
                        )

                    # For daemon mode, we don't have a process to track
                    process = None

                else:
                    # For native Linux (Docker), use foreground mode with process tracking
                    logger.info("Using native Linux foreground mode mounting")
                    process = await self.command_executor.create_subprocess(
                        command=command,
                        env=env,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                # Wait for the mount to become ready
                logger.info("Waiting for mount to become ready...")
                mount_ready = False

                # Give the mount a moment to initialize
                await asyncio.sleep(2)

                # Check if mount is ready
                for attempt in range(15):  # Try for up to 15 seconds
                    # For foreground mode (Docker), check if process has exited with error
                    if process is not None and process.returncode is not None:
                        try:
                            stderr_bytes = (
                                await process.stderr.read() if process.stderr else b""
                            )
                            stdout_bytes = (
                                await process.stdout.read() if process.stdout else b""
                            )
                            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
                            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                            logger.error(
                                f"Mount process exited with code: {process.returncode}"
                            )
                            logger.error(f"Mount stderr: {stderr_str}")
                            logger.error(f"Mount stdout: {stdout_str}")
                            raise Exception(
                                f"Mount failed: {stderr_str or stdout_str or 'Process exited unexpectedly'}"
                            )
                        except Exception as e:
                            if "Mount failed:" in str(e):
                                raise
                            raise Exception(f"Mount process failed: {e}")

                    # Check if mount point is accessible (works for both daemon and foreground mode)
                    if await self._verify_mount_ready(mount_point):
                        mount_ready = True
                        logger.info(f"Mount ready after {attempt + 1} second(s)")
                        break

                    await asyncio.sleep(1)

                if not mount_ready:
                    # Clean up based on mount type
                    if process is not None and process.returncode is None:
                        # Foreground mode - kill the process
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5)
                        except asyncio.TimeoutError:
                            process.kill()

                    # Always try to unmount
                    await self._unmount_path(mount_point)
                    raise Exception(
                        f"Mount point {mount_point} did not become accessible within 15 seconds"
                    )

                mount_info = MountInfo(
                    repository_path=repository.path,
                    archive_name=archive_name,
                    mount_point=mount_point,
                    mounted_at=now_utc(),
                    last_accessed=now_utc(),
                    temp_keyfile_path=temp_keyfile_path,
                    process=process,
                )
                self.active_mounts[mount_key] = mount_info

                logger.info(f"Successfully mounted archive at {mount_point}")
                return mount_point

        except Exception as e:
            logger.error(f"Failed to mount archive {archive_name}: {e}")
            try:
                if mount_point.exists():
                    await self._unmount_path(mount_point)
            except Exception:
                pass
            raise Exception(f"Failed to mount archive: {str(e)}")

    async def _is_mounted(self, mount_point: Path) -> bool:
        """Check if mount point has actual archive contents"""
        try:
            # Use ls to check if directory exists and has contents
            result = await self.command_executor.execute_command(
                command=[
                    "ls",
                    "-A",
                    mount_point.as_posix(),
                ],  # -A shows all except . and ..
                timeout=5.0,
            )

            # If ls succeeds and has output, the mount point has contents
            return result.success and bool(result.stdout.strip())

        except Exception:
            return False

    async def _unmount_path(self, mount_point: Path) -> bool:
        """Unmount a filesystem path"""
        try:
            # Try fusermount first (most common)
            result = await self.command_executor.execute_command(
                command=["fusermount", "-u", mount_point.as_posix()], timeout=10.0
            )

            if not result.success:
                # Try fusermount3 (newer systems)
                result = await self.command_executor.execute_command(
                    command=["fusermount3", "-u", mount_point.as_posix()], timeout=10.0
                )

            if result.success:
                # Remove the mount point directory using command executor
                await self.command_executor.execute_command(
                    command=["rmdir", mount_point.as_posix()], timeout=5.0
                )
                return True
            else:
                logger.error(f"Failed to unmount {mount_point}: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error unmounting {mount_point}: {e}")
            return False

    async def _cleanup_all_lingering_mounts(self) -> None:
        """Clean up any lingering mounts and directories from previous crashes"""
        try:
            logger.info(
                f"Cleaning up lingering mounts in {self.base_mount_dir.as_posix()}"
            )

            # First, try to list all directories in the base mount directory
            result = await self.command_executor.execute_command(
                command=[
                    "find",
                    self.base_mount_dir.as_posix(),
                    "-type",
                    "d",
                    "-mindepth",
                    "1",
                    "-maxdepth",
                    "1",
                ],
                timeout=10.0,
            )

            if result.success and result.stdout.strip():
                mount_dirs = result.stdout.strip().split("\n")
                logger.info(
                    f"Found {len(mount_dirs)} potential mount directories to clean up"
                )

                for mount_dir in mount_dirs:
                    if not mount_dir.strip():
                        continue

                    logger.info(f"Attempting to unmount and clean up: {mount_dir}")

                    # Try to unmount (this will fail silently if not mounted)
                    await self._force_unmount_directory(mount_dir.strip())

                    # Remove the directory
                    await self._remove_directory(mount_dir.strip())

            # Finally, ensure the base directory exists but is empty
            await self.command_executor.execute_command(
                command=["mkdir", "-p", self.base_mount_dir.as_posix()], timeout=5.0
            )

            logger.info("Lingering mount cleanup completed")

        except Exception as e:
            logger.warning(f"Error during lingering mount cleanup: {e}")
            # Don't fail startup if cleanup has issues

    async def _force_unmount_directory(self, mount_dir: str) -> None:
        """Force unmount a directory, trying multiple methods"""
        try:
            # Try fusermount first
            result = await self.command_executor.execute_command(
                command=["fusermount", "-u", mount_dir], timeout=10.0
            )

            if not result.success:
                # Try fusermount3
                result = await self.command_executor.execute_command(
                    command=["fusermount3", "-u", mount_dir], timeout=10.0
                )

            if not result.success:
                # Try lazy unmount as last resort
                await self.command_executor.execute_command(
                    command=["fusermount", "-uz", mount_dir], timeout=10.0
                )

        except Exception as e:
            logger.warning(f"Could not unmount {mount_dir}: {e}")

    async def _remove_directory(self, mount_dir: str) -> None:
        """Remove a directory, handling various edge cases"""
        try:
            # First try a simple rmdir
            result = await self.command_executor.execute_command(
                command=["rmdir", mount_dir], timeout=5.0
            )

            if not result.success:
                # If rmdir fails, the directory might not be empty or might be a mount point
                # Try to remove contents first, then the directory
                await self.command_executor.execute_command(
                    command=["rm", "-rf", mount_dir], timeout=10.0
                )

        except Exception as e:
            logger.warning(f"Could not remove directory {mount_dir}: {e}")

    async def list_directory(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[ArchiveEntry]:
        """List directory contents from mounted filesystem"""
        mount_key = self._get_mount_key(repository, archive_name)

        if mount_key not in self.active_mounts:
            raise Exception(f"Archive {archive_name} is not mounted")

        mount_info = self.active_mounts[mount_key]
        mount_info.last_accessed = now_utc()

        # Build the full path using POSIX format
        target_path_posix = mount_info.mount_point.as_posix()
        if path.strip():
            # Ensure path starts with / and join properly
            clean_path = path.strip().lstrip("/")
            target_path_posix = f"{target_path_posix}/{clean_path}"

        try:
            # Use ls -la to get detailed directory listing through command executor
            result = await self.command_executor.execute_command(
                command=["ls", "-la", target_path_posix], timeout=10.0
            )

            if not result.success:
                if "No such file or directory" in result.stderr:
                    raise Exception(f"Path does not exist: {path}")
                elif "Not a directory" in result.stderr:
                    raise Exception(f"Path is not a directory: {path}")
                else:
                    raise Exception(f"Failed to list directory: {result.stderr}")

            entries = []
            lines = result.stdout.strip().split("\n")

            # Skip the first line (total) and parse each entry
            for line in lines[1:] if len(lines) > 1 else []:
                if not line.strip():
                    continue

                try:
                    # Parse ls -la output: permissions, links, owner, group, size, date, name
                    parts = line.split(None, 8)  # Split on whitespace, max 9 parts
                    if len(parts) < 9:
                        continue

                    permissions = parts[0]
                    size_str = parts[4]
                    name = parts[8]

                    # Skip . and .. entries
                    if name in [".", ".."]:
                        continue

                    # Determine if it's a directory
                    is_directory = permissions.startswith("d")

                    # Parse size
                    try:
                        size = int(size_str) if not is_directory else 0
                    except ValueError:
                        size = 0

                    # Build the relative path
                    if path.strip():
                        relative_path = f"{path.strip().rstrip('/')}/{name}"
                    else:
                        relative_path = name

                    entry = ArchiveEntry(
                        path=relative_path,
                        name=name,
                        type="d" if is_directory else "f",
                        size=size,
                        isdir=is_directory,
                        mode=permissions[1:4],  # Extract user permissions
                        mtime=now_utc().isoformat(),  # We could parse the date from ls output, but this is simpler
                        healthy=True,
                    )
                    entries.append(entry)

                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse ls output line: {line} - {e}")
                    continue

            # Sort: directories first, then files, both alphabetically
            entries.sort(
                key=lambda x: (
                    not x.isdir,
                    x.name.lower(),
                )
            )

            logger.info(f"Listed {len(entries)} items from {target_path_posix}")
            return entries

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            raise Exception(f"Failed to list directory: {str(e)}")

    async def unmount_all(self) -> None:
        """Unmount all active mounts and clean up any lingering mounts from crashes"""
        logger.info(f"Unmounting {len(self.active_mounts)} active mounts")

        # First, unmount all known active mounts
        for mount_key in list(self.active_mounts.keys()):
            mount_info = self.active_mounts[mount_key]

            # Terminate the FUSE process if it's still running (only for foreground mode)
            if mount_info.process and mount_info.process.returncode is None:
                try:
                    logger.info(
                        f"Terminating FUSE process for {mount_info.mount_point}"
                    )
                    mount_info.process.terminate()
                    await asyncio.wait_for(mount_info.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning("Process didn't terminate gracefully, killing it")
                    mount_info.process.kill()
                except Exception as e:
                    logger.warning(f"Error terminating mount process: {e}")
            elif mount_info.process is None:
                logger.info(
                    f"Daemon mode mount detected for {mount_info.mount_point}, no process to terminate"
                )

            await self._unmount_path(mount_info.mount_point)

            # Clean up temporary keyfile
            cleanup_temp_keyfile(mount_info.temp_keyfile_path)

        self.active_mounts.clear()

        # Then, do a comprehensive cleanup of the entire base mount directory
        # This catches any lingering mounts from previous crashes
        await self._cleanup_all_lingering_mounts()

    def get_mount_stats(self) -> MountStatsResponse:
        """Get statistics about active mounts"""
        return MountStatsResponse(
            active_mounts=len(self.active_mounts),
            mounts=[
                MountStatEntry(
                    archive=info.archive_name,
                    mount_point=str(info.mount_point),
                    mounted_at=info.mounted_at.isoformat(),
                    last_accessed=info.last_accessed.isoformat(),
                )
                for info in self.active_mounts.values()
            ],
        )
