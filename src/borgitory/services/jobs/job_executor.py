"""
Job Executor Module - Handles subprocess execution and process management
"""

import asyncio
import logging
import re
import inspect
from typing import Dict, List, Optional, Callable, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from borgitory.constants.retention import RetentionFieldHandler
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from borgitory.utils.datetime_utils import now_utc
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.services.cloud_providers.cloud_sync_service import CloudSyncService
from borgitory.utils.security import create_borg_command

logger = logging.getLogger(__name__)


class JobExecutor:
    """Handles subprocess execution and output monitoring"""

    def __init__(
        self,
        command_executor: CommandExecutorProtocol,
    ) -> None:
        self.command_executor = command_executor
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    async def start_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """Start a subprocess with the given command"""
        try:
            logger.info(f"Starting process: {' '.join(command[:3])}...")

            # Use the new command executor for cross-platform compatibility
            process = await self.command_executor.create_subprocess(
                command=command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )

            logger.info(f"Process started with PID: {process.pid}")
            return process

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            raise

    async def monitor_process_output(
        self,
        process: asyncio.subprocess.Process,
        output_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> ProcessResult:
        """Monitor process output and return final result"""
        stdout_data = b""
        stderr_data = b""

        try:
            if process.stdout:
                async for line in process.stdout:
                    line_text = line.decode("utf-8", errors="replace").rstrip()
                    stdout_data += line

                    progress_info = self.parse_progress_line(line_text)

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

            return_code = await process.wait()

            return ProcessResult(
                return_code=return_code, stdout=stdout_data, stderr=stderr_data
            )

        except Exception as e:
            error_msg = f"Process monitoring error: {e}"
            logger.error(error_msg)
            return ProcessResult(
                return_code=-1, stdout=stdout_data, stderr=stderr_data, error=error_msg
            )

    def parse_progress_line(self, line: str) -> Dict[str, object]:
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

    async def terminate_process(
        self, process: asyncio.subprocess.Process, timeout: float = 5.0
    ) -> bool:
        """Terminate a process gracefully, then force kill if needed"""
        try:
            if process.returncode is None:
                if hasattr(process, "terminate") and callable(process.terminate):
                    if asyncio.iscoroutinefunction(process.terminate):
                        await process.terminate()
                    else:
                        process.terminate()

                try:
                    await asyncio.wait_for(process.wait(), timeout=timeout)
                    logger.info("Process terminated gracefully")
                    return True
                except asyncio.TimeoutError:
                    logger.warning(
                        "Process did not terminate gracefully, force killing"
                    )
                    if hasattr(process, "kill") and callable(process.kill):
                        if asyncio.iscoroutinefunction(process.kill):
                            await process.kill()
                        else:
                            process.kill()
                    await process.wait()
                    logger.info("Process force killed")
                    return True
            else:
                logger.info("Process already terminated")
                return True

        except Exception as e:
            logger.error(f"Error terminating process: {e}")
            return False

    def format_command_for_logging(self, command: List[str]) -> str:
        """Format command for safe logging (hide sensitive info)"""
        safe_command = []
        skip_next = False

        for i, arg in enumerate(command):
            if skip_next:
                safe_command.append("[REDACTED]")
                skip_next = False
            elif arg in ["--encryption-passphrase", "-p", "--passphrase"]:
                safe_command.append(arg)
                skip_next = True
            elif "::" in arg and len(arg.split("::")) == 2:
                parts = arg.split("::")
                safe_command.append(f"{parts[0]}::[ARCHIVE]")
            else:
                safe_command.append(arg)

        return " ".join(safe_command)

    async def execute_prune_task(
        self,
        repository_path: str,
        passphrase: str,
        keyfile_content: Optional[str] = None,
        keep_within: Optional[str] = None,
        keep_secondly: Optional[int] = None,
        keep_minutely: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,
        show_stats: bool = True,
        show_list: bool = False,
        save_space: bool = False,
        force_prune: bool = False,
        dry_run: bool = False,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ProcessResult:
        """
        Execute a borg prune task with the job executor's proper streaming

        Args:
            repository_path: Path to the borg repository
            passphrase: Repository passphrase
            keep_within: Keep archives within this time range
            keep_secondly: Number of secondly archives to keep
            keep_minutely: Number of minutely archives to keep
            keep_hourly: Number of hourly archives to keep
            keep_daily: Number of daily archives to keep
            keep_weekly: Number of weekly archives to keep
            keep_monthly: Number of monthly archives to keep
            keep_yearly: Number of yearly archives to keep
            show_stats: Show statistics
            show_list: Show list of archives
            save_space: Use save-space option
            force_prune: Force pruning
            dry_run: Perform dry run
            output_callback: Callback for streaming output

        Returns:
            ProcessResult with execution details
        """
        try:
            additional_args = []

            retention_args = RetentionFieldHandler.build_borg_args_explicit(
                keep_within=keep_within,
                keep_secondly=keep_secondly,
                keep_minutely=keep_minutely,
                keep_hourly=keep_hourly,
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_yearly=keep_yearly,
                include_keep_within=True,
            )
            additional_args.extend(retention_args)
            if show_stats:
                additional_args.append("--stats")
            if show_list:
                additional_args.append("--list")
            if save_space:
                additional_args.append("--save-space")
            if force_prune:
                additional_args.append("--force")
            if dry_run:
                additional_args.append("--dry-run")

            additional_args.append(repository_path)

            logger.info(
                f"Starting borg prune - Repository: {repository_path}, Dry run: {dry_run}"
            )

            borg_command = create_borg_command(
                base_command="borg prune",
                repository_path="",  # Path is in additional_args
                passphrase=passphrase,
                additional_args=additional_args,
            )
            process = await self.start_process(
                borg_command.command, borg_command.environment
            )

            result = await self.monitor_process_output(process, output_callback)

            if result.return_code == 0:
                logger.info("Prune task completed successfully")
            else:
                logger.error(f"Prune task failed with return code {result.return_code}")

            return result

        except Exception as e:
            logger.error(f"Exception in prune task: {str(e)}")
            return ProcessResult(
                return_code=-1, stdout=b"", stderr=str(e).encode(), error=str(e)
            )

    async def execute_compact_task(
        self,
        repository_path: str,
        passphrase: str,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ProcessResult:
        """
        Execute a borg compact task

        Args:
            repository_path: Path to the borg repository
            passphrase: Repository passphrase
            keyfile_content: Optional keyfile content
            output_callback: Callback for streaming output

        Returns:
            ProcessResult with execution details
        """
        try:
            additional_args = ["--progress", repository_path]

            logger.info(f"Starting borg compact - Repository: {repository_path}")

            borg_command = create_borg_command(
                base_command="borg compact",
                repository_path="",
                passphrase=passphrase,
                additional_args=additional_args,
            )
            process = await self.start_process(
                borg_command.command, borg_command.environment
            )

            result = await self.monitor_process_output(process, output_callback)

            if result.return_code == 0:
                logger.info("Compact task completed successfully")
            else:
                logger.error(
                    f"Compact task failed with return code {result.return_code}"
                )

            return result

        except Exception as e:
            logger.error(f"Exception in compact task: {str(e)}")
            return ProcessResult(
                return_code=-1, stdout=b"", stderr=str(e).encode(), error=str(e)
            )

    async def execute_cloud_sync_task(
        self,
        repository_path: str,
        cloud_sync_config_id: int,
        session_maker: "async_sessionmaker[AsyncSession]",
        cloud_sync_service: CloudSyncService,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ProcessResult:
        """
        Execute a cloud sync task using CloudSyncService.

        This method now delegates all cloud sync logic to CloudSyncService,
        which provides a clean, unified interface for all providers.

        Args:
            repository_path: Path to the borg repository
            cloud_sync_config_id: ID of the cloud sync configuration
            session_maker: Async session maker for database sessions
            cloud_sync_service: Cloud sync service for executing the sync
            output_callback: Optional callback for streaming output

        Returns:
            ProcessResult with execution details
        """
        try:
            logger.info(f"Starting cloud sync for repository {repository_path}")

            if output_callback:
                output_callback("Starting cloud sync...")

            async with session_maker() as db:
                result = await cloud_sync_service.execute_sync_from_db(
                    config_id=cloud_sync_config_id,
                    repository_path=repository_path,
                    db=db,
                    output_callback=output_callback,
                )

                if result.success:
                    logger.info("Cloud sync completed successfully")
                    return ProcessResult(
                        return_code=0,
                        stdout=b"Cloud sync completed successfully",
                        stderr=b"",
                        error=None,
                    )
                else:
                    error_msg = result.error or "Cloud sync failed"
                    logger.error(f"Cloud sync failed: {error_msg}")
                    return ProcessResult(
                        return_code=1,
                        stdout=b"",
                        stderr=error_msg.encode(),
                        error=error_msg,
                    )

        except Exception as e:
            error_msg = f"Exception in cloud sync task: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if output_callback:
                output_callback(error_msg)
            return ProcessResult(
                return_code=-1, stdout=b"", stderr=str(e).encode(), error=str(e)
            )
