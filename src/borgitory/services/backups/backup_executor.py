"""
BackupExecutor - Consolidated backup execution with integrated output handling and events

This service consolidates the functionality of:
- JobExecutor (process execution)
- JobOutputManager (output capture)
- JobEventBroadcaster (event notifications)

Into a single, simplified service that directly executes backup operations.
"""

import asyncio
import logging
import os
import re
import inspect
from typing import Dict, List, Optional, Callable, Union, Protocol
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from dataclasses import dataclass
from enum import Enum

from borgitory.models.database import Repository
from borgitory.utils.security import build_secure_borg_command
from borgitory.constants.retention import RetentionFieldHandler

logger = logging.getLogger(__name__)


class SubprocessExecutorProtocol(Protocol):
    """Protocol for subprocess executors"""

    async def __call__(
        self,
        *args: str,
        stdout: Optional[int] = None,
        stderr: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process: ...


class BackupStatus(Enum):
    """Status of backup operations"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BackupConfig:
    """Configuration for backup operations"""

    source_paths: List[str]
    archive_name: Optional[str] = None
    compression: str = "zstd"
    excludes: Optional[List[str]] = None
    dry_run: bool = False
    show_stats: bool = True
    show_list: bool = True

    def __post_init__(self) -> None:
        if self.excludes is None:
            self.excludes = []
        if self.archive_name is None:
            self.archive_name = f"backup-{now_utc().strftime('%Y%m%d-%H%M%S')}"


@dataclass
class PruneConfig:
    """Configuration for prune operations"""

    keep_within: Optional[str] = None
    keep_secondly: Optional[int] = None
    keep_minutely: Optional[int] = None
    keep_hourly: Optional[int] = None
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
    dry_run: bool = False
    show_stats: bool = True
    show_list: bool = False


@dataclass
class BackupResult:
    """Result of a backup operation"""

    status: BackupStatus
    return_code: int
    output_lines: List[str]
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        """Check if the operation was successful"""
        return self.status == BackupStatus.COMPLETED and self.return_code == 0


class BackupExecutor:
    """
    Consolidated backup executor with integrated output handling and event broadcasting.

    Simplifies the backup execution flow by eliminating the need for separate
    JobExecutor, JobOutputManager, and JobEventBroadcaster services.
    """

    def __init__(
        self, subprocess_executor: Optional[SubprocessExecutorProtocol] = None
    ) -> None:
        self.subprocess_executor = subprocess_executor or asyncio.create_subprocess_exec
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

        self.active_operations: Dict[str, asyncio.subprocess.Process] = {}

    async def execute_backup(
        self,
        repository: Repository,
        config: BackupConfig,
        operation_id: Optional[str] = None,
        output_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[
            Callable[[Dict[str, Union[str, int, float]]], None]
        ] = None,
    ) -> BackupResult:
        """
        Execute a backup operation with integrated output handling.

        Args:
            repository: Repository to backup to
            config: Backup configuration
            operation_id: Optional ID for tracking the operation
            output_callback: Optional callback for real-time output
            progress_callback: Optional callback for progress updates

        Returns:
            BackupResult with operation status and details
        """
        result = BackupResult(
            status=BackupStatus.RUNNING,
            return_code=-1,
            output_lines=[],
            started_at=now_utc(),
        )

        if not operation_id:
            operation_id = f"backup-{now_utc().strftime('%Y%m%d-%H%M%S')}"

        logger.info(
            f"Starting backup operation {operation_id} for repository {repository.name}"
        )

        try:
            if not config.source_paths:
                raise ValueError("No source paths specified for backup")

            command, env = self._build_backup_command(repository, config)

            logger.info(f"Executing backup command for {repository.name}")
            logger.debug(f"Backup command: {' '.join(command[:3])}... (args redacted)")

            process = await self._start_process(command, env)

            if operation_id:
                self.active_operations[operation_id] = process

            await self._monitor_process_output(
                process, result, output_callback, progress_callback
            )

            return_code = await process.wait()
            result.return_code = return_code
            result.completed_at = now_utc()

            if return_code == 0:
                result.status = BackupStatus.COMPLETED
                logger.info(f"Backup operation {operation_id} completed successfully")
            else:
                result.status = BackupStatus.FAILED
                if result.output_lines:
                    error_lines = result.output_lines[-5:]
                    result.error_message = (
                        f"Backup failed (exit code {return_code}): "
                        + "\n".join(error_lines)
                    )
                else:
                    result.error_message = f"Backup failed with exit code {return_code}"

                logger.error(
                    f"Backup operation {operation_id} failed: {result.error_message}"
                )

            return result

        except Exception as e:
            result.status = BackupStatus.FAILED
            result.return_code = -1
            result.completed_at = now_utc()
            result.error_message = f"Backup operation failed: {str(e)}"
            logger.error(f"Backup operation {operation_id} failed with exception: {e}")
            return result

        finally:
            if operation_id in self.active_operations:
                del self.active_operations[operation_id]

    async def execute_prune(
        self,
        repository: Repository,
        config: PruneConfig,
        operation_id: Optional[str] = None,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> BackupResult:
        """
        Execute a prune operation with integrated output handling.

        Args:
            repository: Repository to prune
            config: Prune configuration
            operation_id: Optional ID for tracking the operation
            output_callback: Optional callback for real-time output

        Returns:
            BackupResult with operation status and details
        """
        result = BackupResult(
            status=BackupStatus.RUNNING,
            return_code=-1,
            output_lines=[],
            started_at=now_utc(),
        )

        if not operation_id:
            operation_id = f"prune-{now_utc().strftime('%Y%m%d-%H%M%S')}"

        logger.info(
            f"Starting prune operation {operation_id} for repository {repository.name}"
        )

        try:
            command, env = self._build_prune_command(repository, config)

            logger.info(f"Executing prune command for {repository.name}")

            process = await self._start_process(command, env)

            if operation_id:
                self.active_operations[operation_id] = process

            await self._monitor_process_output(process, result, output_callback, None)

            return_code = await process.wait()
            result.return_code = return_code
            result.completed_at = now_utc()

            if return_code == 0:
                result.status = BackupStatus.COMPLETED
                logger.info(f"Prune operation {operation_id} completed successfully")
            else:
                result.status = BackupStatus.FAILED
                if result.output_lines:
                    error_lines = result.output_lines[-5:]
                    result.error_message = (
                        f"Prune failed (exit code {return_code}): "
                        + "\n".join(error_lines)
                    )
                else:
                    result.error_message = f"Prune failed with exit code {return_code}"

                logger.error(
                    f"Prune operation {operation_id} failed: {result.error_message}"
                )

            return result

        except Exception as e:
            result.status = BackupStatus.FAILED
            result.return_code = -1
            result.completed_at = now_utc()
            result.error_message = f"Prune operation failed: {str(e)}"
            logger.error(f"Prune operation {operation_id} failed with exception: {e}")
            return result

        finally:
            if operation_id in self.active_operations:
                del self.active_operations[operation_id]

    async def _start_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """Start a subprocess with the given command"""
        try:
            logger.debug(f"Starting process: {' '.join(command[:3])}...")

            # Merge environment variables
            merged_env = os.environ.copy()
            if env:
                merged_env.update(env)

            process = await self.subprocess_executor(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Redirect stderr to stdout
                env=merged_env,
                cwd=cwd,
            )

            logger.debug(f"Process started with PID: {process.pid}")
            return process

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            raise

    async def _monitor_process_output(
        self,
        process: asyncio.subprocess.Process,
        result: BackupResult,
        output_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[
            Callable[[Dict[str, Union[str, int, float]]], None]
        ] = None,
    ) -> bytes:
        """Monitor process output and capture it in the result"""
        stdout_data = b""

        try:
            if process.stdout:
                async for line in process.stdout:
                    line_text = line.decode("utf-8", errors="replace").rstrip()
                    stdout_data += line

                    result.output_lines.append(line_text)

                    progress_info = self._parse_progress_line(line_text)

                    if output_callback:
                        if inspect.iscoroutinefunction(output_callback):
                            await output_callback(line_text)
                        else:
                            output_callback(line_text)

                    if progress_callback and progress_info:
                        if inspect.iscoroutinefunction(progress_callback):
                            await progress_callback(progress_info)
                        else:
                            progress_callback(progress_info)

            return stdout_data

        except Exception as e:
            error_msg = f"Process monitoring error: {e}"
            logger.error(error_msg)
            result.error_message = error_msg
            return stdout_data

    def _parse_progress_line(self, line: str) -> Dict[str, Union[str, int, float]]:
        """Parse Borg output line for progress information"""
        progress_info = {}

        try:
            match = self.progress_pattern.search(line)
            if match:
                progress_info = {
                    "original_size": int(match.group("original_size")),
                    "compressed_size": int(match.group("compressed_size")),
                    "deduplicated_size": int(match.group("deduplicated_size")),
                    "nfiles": int(match.group("nfiles")),
                    "path": match.group("path").strip(),
                    "timestamp": now_utc().isoformat(),
                }

            elif "Archive name:" in line:
                progress_info["archive_name"] = line.split("Archive name:")[-1].strip()
            elif "Archive fingerprint:" in line:
                progress_info["fingerprint"] = line.split("Archive fingerprint:")[
                    -1
                ].strip()
            elif "Time (start):" in line:
                progress_info["start_time"] = line.split("Time (start):")[-1].strip()
            elif "Time (end):" in line:
                progress_info["end_time"] = line.split("Time (end):")[-1].strip()

        except Exception as e:
            logger.debug(f"Error parsing progress line '{line}': {e}")

        return progress_info

    def _build_backup_command(
        self, repository: Repository, config: BackupConfig
    ) -> tuple[List[str], Dict[str, str]]:
        """Build Borg backup command with arguments"""
        additional_args = []

        if config.show_stats:
            additional_args.append("--stats")
        if config.show_list:
            additional_args.append("--list")

        additional_args.extend(["--filter", "AME"])  # Show added, modified, errors

        if config.compression:
            additional_args.extend(["--compression", config.compression])

        if config.excludes:
            for exclude in config.excludes:
                additional_args.extend(["--exclude", exclude])

        if config.dry_run:
            additional_args.append("--dry-run")

        additional_args.append(f"{repository.path}::{config.archive_name}")

        additional_args.extend(config.source_paths)

        return build_secure_borg_command(
            base_command="borg create",
            repository_path="",  # Already included in additional_args
            passphrase=repository.get_passphrase(),
            additional_args=additional_args,
        )

    def _build_prune_command(
        self, repository: Repository, config: PruneConfig
    ) -> tuple[List[str], Dict[str, str]]:
        """Build Borg prune command with arguments"""
        additional_args = []

        retention_args = RetentionFieldHandler.build_borg_args(
            config, include_keep_within=True
        )
        additional_args.extend(retention_args)

        if config.show_stats:
            additional_args.append("--stats")
        if config.show_list:
            additional_args.append("--list")
        if config.dry_run:
            additional_args.append("--dry-run")

        additional_args.append(repository.path)

        return build_secure_borg_command(
            base_command="borg prune",
            repository_path="",  # Already included in additional_args
            passphrase=repository.get_passphrase(),
            additional_args=additional_args,
        )

    async def terminate_operation(
        self, operation_id: str, timeout: float = 5.0
    ) -> bool:
        """Terminate an active operation gracefully"""
        if operation_id not in self.active_operations:
            logger.warning(f"Operation {operation_id} not found in active operations")
            return False

        process = self.active_operations[operation_id]

        try:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=timeout)
                    logger.info(f"Operation {operation_id} terminated gracefully")
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Operation {operation_id} did not terminate gracefully, force killing"
                    )
                    process.kill()
                    await process.wait()
                    logger.info(f"Operation {operation_id} force killed")

            del self.active_operations[operation_id]
            return True

        except Exception as e:
            logger.error(f"Error terminating operation {operation_id}: {e}")
            return False

    def get_active_operations(self) -> List[str]:
        """Get list of active operation IDs"""
        return list(self.active_operations.keys())

    def is_operation_active(self, operation_id: str) -> bool:
        """Check if an operation is currently active"""
        return operation_id in self.active_operations
