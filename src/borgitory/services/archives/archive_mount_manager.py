"""
Archive Mount Manager - FUSE-based archive browsing system
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime, timedelta
from borgitory.utils.datetime_utils import now_utc

from borgitory.models.database import Repository
from borgitory.utils.security import build_secure_borg_command
from borgitory.services.jobs.job_executor import JobExecutor

if TYPE_CHECKING:
    from borgitory.services.archives.archive_manager import ArchiveEntry

logger = logging.getLogger(__name__)


@dataclass
class MountInfo:
    """Information about a mounted archive"""

    repository_path: str
    archive_name: str
    mount_point: Path
    mounted_at: datetime
    last_accessed: datetime
    job_executor_process: Optional[asyncio.subprocess.Process] = None


class ArchiveMountManager:
    """Manages FUSE mounts for Borg archives"""

    def __init__(
        self,
        base_mount_dir: Optional[str] = None,
        job_executor: Optional[JobExecutor] = None,
        cleanup_interval: int = 300,
        mount_timeout: int = 1800,
    ) -> None:
        # Use environment variable or sensible default based on platform
        if base_mount_dir is None:
            if os.name == "nt":  # Windows
                base_mount_dir = os.path.join(
                    os.environ.get("TEMP", "C:\\temp"), "borgitory_mounts"
                )
            else:  # Unix-like
                base_mount_dir = "/tmp/borgitory_mounts"

        self.base_mount_dir = Path(base_mount_dir)
        self.base_mount_dir.mkdir(parents=True, exist_ok=True)
        self.active_mounts: Dict[str, MountInfo] = {}  # key: repo_path::archive_name
        self.cleanup_interval = cleanup_interval  # 5 minutes default
        self.mount_timeout = mount_timeout  # 30 minutes before auto-unmount
        self.job_executor = job_executor or JobExecutor()

    def _get_mount_key(self, repository: Repository, archive_name: str) -> str:
        """Generate unique key for mount"""
        return f"{repository.path}::{archive_name}"

    def _get_mount_point(self, repository: Repository, archive_name: str) -> Path:
        """Generate mount point path"""
        safe_repo_name = repository.name.replace("/", "_").replace(" ", "_")
        safe_archive_name = archive_name.replace("/", "_").replace(" ", "_")
        return self.base_mount_dir / f"{safe_repo_name}_{safe_archive_name}"

    async def mount_archive(self, repository: Repository, archive_name: str) -> Path:
        """Mount an archive and return the mount point"""
        mount_key = self._get_mount_key(repository, archive_name)

        # Check if already mounted
        if mount_key in self.active_mounts:
            mount_info = self.active_mounts[mount_key]
            mount_info.last_accessed = datetime.now()
            logger.info(f"Archive already mounted at {mount_info.mount_point}")
            return mount_info.mount_point

        mount_point = self._get_mount_point(repository, archive_name)

        try:
            # Create mount point directory
            mount_point.mkdir(parents=True, exist_ok=True)

            # Build borg mount command
            command, env = build_secure_borg_command(
                base_command="borg mount",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=[
                    f"{repository.path}::{archive_name}",
                    str(mount_point),
                    "-f",  # foreground mode
                ],
            )

            logger.info(f"Mounting archive {archive_name} at {mount_point}")

            # Start borg mount process
            process = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for the mount to establish by polling until it's ready
            mount_ready = await self._wait_for_mount_ready(
                mount_point, process, timeout=5
            )

            if not mount_ready:
                # Try to get error information from the process
                try:
                    # Check if process has already exited with error
                    if process.returncode is not None:
                        stderr_data = (
                            await process.stderr.read() if process.stderr else b""
                        )
                        error_msg = stderr_data.decode("utf-8", errors="replace")
                        raise Exception(f"Mount failed: {error_msg}")
                    else:
                        # Process is still running but mount not ready - terminate it
                        process.terminate()
                        await asyncio.wait_for(process.wait(), timeout=5)
                        stderr_data = (
                            await process.stderr.read() if process.stderr else b""
                        )
                        error_msg = stderr_data.decode("utf-8", errors="replace")
                        raise Exception(f"Mount timed out: {error_msg}")
                except asyncio.TimeoutError:
                    process.kill()
                    raise Exception(
                        "Archive contents not available after 5 seconds - mount failed"
                    )

            # Store mount info
            mount_info = MountInfo(
                repository_path=repository.path,
                archive_name=archive_name,
                mount_point=mount_point,
                mounted_at=now_utc(),
                last_accessed=now_utc(),
                job_executor_process=process,
            )
            self.active_mounts[mount_key] = mount_info

            logger.info(f"Successfully mounted archive at {mount_point}")
            return mount_point

        except Exception as e:
            logger.error(f"Failed to mount archive {archive_name}: {e}")
            # Cleanup on failure
            try:
                if mount_point.exists():
                    await self._unmount_path(mount_point)
            except Exception:
                pass
            raise Exception(f"Failed to mount archive: {str(e)}")

    def _is_mounted(self, mount_point: Path) -> bool:
        """Check if mount point has actual archive contents"""
        try:
            if not mount_point.exists() or not mount_point.is_dir():
                return False

            # Check if directory has actual contents (files/folders)
            contents = list(mount_point.iterdir())
            return len(contents) > 0

        except (OSError, PermissionError):
            return False

    async def _wait_for_mount_ready(
        self, mount_point: Path, process: asyncio.subprocess.Process, timeout: int = 5
    ) -> bool:
        """Wait for mount to have contents, checking every second for up to 5 seconds"""
        for attempt in range(int(timeout)):
            # Check if process has exited with error
            if process.returncode is not None and process.returncode != 0:
                return False

            # Check if mount has contents
            if self._is_mounted(mount_point):
                logger.info(f"Mount ready after {attempt + 1} second(s)")
                return True

            # Wait 1 second before next check
            await asyncio.sleep(1)

        # No contents found after timeout
        return False

    async def unmount_archive(self, repository: Repository, archive_name: str) -> bool:
        """Unmount a specific archive"""
        mount_key = self._get_mount_key(repository, archive_name)

        if mount_key not in self.active_mounts:
            logger.warning(f"Archive {archive_name} is not mounted")
            return False

        mount_info = self.active_mounts[mount_key]
        success = await self._unmount_path(mount_info.mount_point)

        if success:
            # Terminate the borg process
            if mount_info.job_executor_process:
                try:
                    mount_info.job_executor_process.terminate()
                    await asyncio.wait_for(
                        mount_info.job_executor_process.wait(), timeout=5
                    )
                except (ProcessLookupError, asyncio.TimeoutError):
                    # Process already dead or taking too long
                    if mount_info.job_executor_process.returncode is None:
                        mount_info.job_executor_process.kill()

            del self.active_mounts[mount_key]
            logger.info(f"Unmounted archive {archive_name}")

        return success

    async def _unmount_path(self, mount_point: Path) -> bool:
        """Unmount a filesystem path"""
        try:
            # Use fusermount -u to unmount FUSE filesystems
            process = await asyncio.create_subprocess_exec(
                "fusermount",
                "-u",
                str(mount_point),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.wait()

            if process.returncode == 0:
                # Remove the mount point directory
                try:
                    mount_point.rmdir()
                except OSError:
                    pass  # Directory might not be empty or have permissions issues
                return True
            else:
                stderr_data = await process.stderr.read() if process.stderr else b""
                error_msg = stderr_data.decode("utf-8", errors="replace")
                logger.error(f"Failed to unmount {mount_point}: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Error unmounting {mount_point}: {e}")
            return False

    def list_directory(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List["ArchiveEntry"]:
        """List directory contents from mounted filesystem"""
        mount_key = self._get_mount_key(repository, archive_name)

        if mount_key not in self.active_mounts:
            raise Exception(f"Archive {archive_name} is not mounted")

        mount_info = self.active_mounts[mount_key]
        mount_info.last_accessed = datetime.now()

        # Build the full path
        target_path = mount_info.mount_point
        if path.strip():
            target_path = target_path / path.strip().lstrip("/")

        try:
            if not target_path.exists():
                raise Exception(f"Path does not exist: {path}")

            if not target_path.is_dir():
                raise Exception(f"Path is not a directory: {path}")

            entries = []
            for item in target_path.iterdir():
                try:
                    stat_info = item.stat()

                    # Create ArchiveEntry compatible structure
                    is_directory = item.is_dir()
                    entry: "ArchiveEntry" = {
                        "path": str(item.relative_to(mount_info.mount_point)),
                        "name": item.name,
                        "type": "d" if is_directory else "f",
                        "size": stat_info.st_size if item.is_file() else 0,
                        "isdir": is_directory,
                        "mode": oct(stat_info.st_mode)[
                            -4:
                        ],  # Last 4 digits of octal mode
                        "mtime": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                        "healthy": True,
                    }
                    entries.append(entry)

                except (OSError, PermissionError) as e:
                    logger.warning(f"Error reading {item}: {e}")
                    continue

            # Sort: directories first, then files, both alphabetically
            entries.sort(
                key=lambda x: (
                    not x.get("isdir", False),
                    str(x.get("name", "")).lower(),
                )
            )

            logger.info(f"Listed {len(entries)} items from {target_path}")
            return entries

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            raise Exception(f"Failed to list directory: {str(e)}")

    async def cleanup_old_mounts(self) -> None:
        """Remove old unused mounts"""
        cutoff_time = now_utc() - timedelta(seconds=self.mount_timeout)
        to_remove = []

        for mount_key, mount_info in self.active_mounts.items():
            if mount_info.last_accessed < cutoff_time:
                to_remove.append(mount_key)

        for mount_key in to_remove:
            mount_info = self.active_mounts[mount_key]
            logger.info(f"Cleaning up old mount: {mount_info.archive_name}")
            await self._unmount_path(mount_info.mount_point)

            # Terminate process
            if mount_info.job_executor_process:
                try:
                    mount_info.job_executor_process.terminate()
                    await asyncio.wait_for(
                        mount_info.job_executor_process.wait(), timeout=5
                    )
                except (ProcessLookupError, asyncio.TimeoutError):
                    pass

            del self.active_mounts[mount_key]

    async def unmount_all(self) -> None:
        """Unmount all active mounts"""
        logger.info(f"Unmounting {len(self.active_mounts)} active mounts")

        for mount_key in list(self.active_mounts.keys()):
            mount_info = self.active_mounts[mount_key]
            await self._unmount_path(mount_info.mount_point)

            if mount_info.job_executor_process:
                try:
                    mount_info.job_executor_process.terminate()
                    await asyncio.wait_for(
                        mount_info.job_executor_process.wait(), timeout=5
                    )
                except (ProcessLookupError, asyncio.TimeoutError):
                    pass

        self.active_mounts.clear()

    def get_mount_stats(self) -> Dict[str, object]:
        """Get statistics about active mounts"""
        return {
            "active_mounts": len(self.active_mounts),
            "mounts": [
                {
                    "archive": info.archive_name,
                    "mount_point": str(info.mount_point),
                    "mounted_at": info.mounted_at.isoformat(),
                    "last_accessed": info.last_accessed.isoformat(),
                }
                for info in self.active_mounts.values()
            ],
        }
