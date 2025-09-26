"""
Archive Mount Manager - FUSE-based archive browsing system
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING, TypedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from borgitory.utils.datetime_utils import now_utc

from borgitory.models.database import Repository
from borgitory.utils.security import secure_borg_command, cleanup_temp_keyfile
from borgitory.services.archives.archive_manager import ArchiveEntry

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
    job_executor_process: Optional[asyncio.subprocess.Process] = None
    temp_keyfile_path: Optional[str] = None


class ArchiveMountManager:
    """Manages FUSE mounts for Borg archives"""

    def __init__(
        self,
        job_executor: "ProcessExecutorProtocol",
        base_mount_dir: str,
        mount_timeout: timedelta = timedelta(seconds=1800),
        mounting_timeout: timedelta = timedelta(seconds=30),
    ) -> None:
        self.base_mount_dir = Path(base_mount_dir)
        self.base_mount_dir.mkdir(parents=True, exist_ok=True)
        self.active_mounts: Dict[str, MountInfo] = {}  # key: repo_path::archive_name
        self.mount_timeout = mount_timeout
        self.mounting_timeout = mounting_timeout
        self.job_executor = job_executor

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

        if mount_key in self.active_mounts:
            mount_info = self.active_mounts[mount_key]
            mount_info.last_accessed = now_utc()
            logger.info(f"Archive already mounted at {mount_info.mount_point}")
            return mount_info.mount_point

        mount_point = self._get_mount_point(repository, archive_name)

        try:
            mount_point.mkdir(parents=True, exist_ok=True)

            logger.info(f"Mounting archive {archive_name} at {mount_point}")

            async with secure_borg_command(
                base_command="borg mount",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=[
                    f"{repository.path}::{archive_name}",
                    str(mount_point),
                    "-f",  # foreground mode
                ],
                cleanup_keyfile=False,
            ) as (command, env, temp_keyfile_path):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                mount_ready = await self._wait_for_mount_ready(
                    mount_point, process, self.mounting_timeout.seconds
                )

                if not mount_ready:
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

                mount_info = MountInfo(
                    repository_path=repository.path,
                    archive_name=archive_name,
                    mount_point=mount_point,
                    mounted_at=now_utc(),
                    last_accessed=now_utc(),
                    job_executor_process=process,
                    temp_keyfile_path=temp_keyfile_path,
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

    def _is_mounted(self, mount_point: Path) -> bool:
        """Check if mount point has actual archive contents"""
        try:
            if not mount_point.exists() or not mount_point.is_dir():
                return False

            contents = list(mount_point.iterdir())
            return len(contents) > 0

        except (OSError, PermissionError):
            return False

    async def _wait_for_mount_ready(
        self, mount_point: Path, process: asyncio.subprocess.Process, timeout: int = 5
    ) -> bool:
        """Wait for mount to have contents, checking every second up to timeout"""
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

            cleanup_temp_keyfile(mount_info.temp_keyfile_path)

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
    ) -> List[ArchiveEntry]:
        """List directory contents from mounted filesystem"""
        mount_key = self._get_mount_key(repository, archive_name)

        if mount_key not in self.active_mounts:
            raise Exception(f"Archive {archive_name} is not mounted")

        mount_info = self.active_mounts[mount_key]
        mount_info.last_accessed = now_utc()

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
                    entry = ArchiveEntry(
                        path=str(item.relative_to(mount_info.mount_point)),
                        name=item.name,
                        type="d" if is_directory else "f",
                        size=stat_info.st_size if item.is_file() else 0,
                        isdir=is_directory,
                        mode=oct(stat_info.st_mode)[-4:],  # Last 4 digits of octal mode
                        mtime=datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                        healthy=True,
                    )
                    entries.append(entry)

                except (OSError, PermissionError) as e:
                    logger.warning(f"Error reading {item}: {e}")
                    continue

            # Sort: directories first, then files, both alphabetically
            entries.sort(
                key=lambda x: (
                    not x.isdir,
                    x.name.lower(),
                )
            )

            logger.info(f"Listed {len(entries)} items from {target_path}")
            return entries

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            raise Exception(f"Failed to list directory: {str(e)}")

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

            cleanup_temp_keyfile(mount_info.temp_keyfile_path)

        self.active_mounts.clear()

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
