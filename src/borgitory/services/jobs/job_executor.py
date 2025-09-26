"""
Job Executor Module - Handles subprocess execution and process management
"""

import asyncio
import json
import logging
import os
import re
import inspect
from typing import Dict, List, Optional, Callable, Coroutine, TYPE_CHECKING, cast

from borgitory.constants.retention import RetentionFieldHandler
from borgitory.utils.security import secure_borg_command

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
from borgitory.utils.datetime_utils import now_utc
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.services.rclone_service import RcloneService
from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.cloud_providers.service import StorageFactory
from borgitory.services.encryption_service import EncryptionService
from borgitory.custom_types import ConfigDict

logger = logging.getLogger(__name__)


class JobExecutor:
    """Handles subprocess execution and output monitoring"""

    def __init__(
        self,
        subprocess_executor: Optional[
            Callable[..., Coroutine[None, None, asyncio.subprocess.Process]]
        ] = None,
    ) -> None:
        self.subprocess_executor = subprocess_executor or asyncio.create_subprocess_exec
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

            merged_env = os.environ.copy()
            if env:
                merged_env.update(env)

            process = await self.subprocess_executor(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
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

            async with secure_borg_command(
                base_command="borg prune",
                repository_path="",  # Path is in additional_args
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=additional_args,
            ) as (command, env, _):
                process = await self.start_process(command, env)

                result = await self.monitor_process_output(process, output_callback)

                if result.return_code == 0:
                    logger.info("Prune task completed successfully")
                else:
                    logger.error(
                        f"Prune task failed with return code {result.return_code}"
                    )

                return result

        except Exception as e:
            logger.error(f"Exception in prune task: {str(e)}")
            return ProcessResult(
                return_code=-1, stdout=b"", stderr=str(e).encode(), error=str(e)
            )

    async def execute_cloud_sync_task(
        self,
        repository_path: str,
        cloud_sync_config_id: int,
        db_session_factory: Callable[[], "Session"],
        rclone_service: RcloneService,
        encryption_service: EncryptionService,
        storage_factory: StorageFactory,
        provider_registry: ProviderRegistry,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ProcessResult:
        """
        Execute a cloud sync task with the job executor's proper streaming

        Args:
            repository_path: Path to the borg repository
            cloud_sync_config_id: ID of the cloud sync configuration
            db_session_factory: Factory for database sessions (required)
            rclone_service: Rclone service instance for cloud operations (required)
            encryption_service: Service for encrypting/decrypting sensitive fields (required)
            storage_factory: Factory for creating cloud storage instances (required)
            provider_registry: Registry for cloud providers (required)
            output_callback: Optional callback for streaming output

        Returns:
            ProcessResult with execution details
        """
        try:
            from borgitory.models.database import CloudSyncConfig

            session_factory = db_session_factory

            logger.info(f"Starting cloud sync for repository {repository_path}")

            if output_callback:
                output_callback("Starting cloud sync...")

            with session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == cloud_sync_config_id)
                    .first()
                )

                if not config or not config.enabled:
                    logger.info(
                        "Cloud backup configuration not found or disabled - skipping"
                    )
                    if output_callback:
                        output_callback(
                            "Cloud backup configuration not found or disabled - skipping"
                        )
                    return ProcessResult(
                        return_code=0,
                        stdout=b"Cloud sync skipped - configuration disabled",
                        stderr=b"",
                        error=None,
                    )

                try:
                    from borgitory.models.database import Repository

                    if not config.provider_config:
                        raise ValueError(
                            f"Cloud sync configuration '{config.name}' has no provider_config. "
                            f"Please update the configuration through the web UI to add the required "
                            f"connection details for {config.provider.upper()}."
                        )

                    try:
                        encrypted_config = json.loads(config.provider_config)
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"Cloud sync configuration '{config.name}' has invalid JSON in provider_config: {e}"
                        )

                    # Validate that we have some configuration
                    if not encrypted_config or not isinstance(encrypted_config, dict):
                        raise ValueError(
                            f"Cloud sync configuration '{config.name}' has empty or invalid provider_config. "
                            f"Please update the configuration through the web UI."
                        )

                    # Get sensitive fields by creating a temporary storage with dummy config
                    metadata = provider_registry.get_metadata(config.provider)
                    if not metadata:
                        raise ValueError(f"Unknown provider: {config.provider}")

                    # Create minimal dummy config to get sensitive fields
                    if config.provider == "s3":
                        dummy_config = {
                            "access_key": "AKIAIOSFODNN7EXAMPLE",
                            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                            "bucket_name": "dummy-bucket",
                        }
                    elif config.provider == "sftp":
                        dummy_config = {
                            "host": "dummy.example.com",
                            "username": "dummy",
                            "remote_path": "/dummy",
                            "password": "dummy_password",
                        }
                    elif config.provider == "smb":
                        dummy_config = {
                            "host": "dummy.example.com",
                            "user": "dummy",
                            "pass": "dummy",
                            "share_name": "dummy",
                        }
                    else:
                        raise ValueError(
                            f"Unsupported provider for decryption: {config.provider}"
                        )

                    # Create temporary storage to get sensitive fields
                    temp_storage = storage_factory.create_storage(
                        config.provider, cast(ConfigDict, dummy_config)
                    )
                    sensitive_fields = temp_storage.get_sensitive_fields()

                    # Decrypt the configuration
                    provider_config = encryption_service.decrypt_sensitive_fields(
                        encrypted_config, sensitive_fields
                    )

                    # Add path prefix if specified
                    if config.path_prefix:
                        provider_config["path_prefix"] = config.path_prefix

                    # Create repository object for rclone service
                    repo_obj = Repository()
                    repo_obj.path = repository_path

                    logger.info(f"Syncing to {config.name} ({config.provider.upper()})")
                    if output_callback:
                        output_callback(
                            f"Syncing to {config.name} ({config.provider.upper()})"
                        )

                    # Use the generic rclone dispatcher
                    progress_generator = rclone_service.sync_repository_to_provider(
                        provider=config.provider,
                        repository=repo_obj,
                        **provider_config,  # type: ignore[arg-type]
                    )

                except Exception as e:
                    error_msg = f"Failed to initialize cloud provider {config.provider}: {str(e)}"
                    logger.error(error_msg)
                    if output_callback:
                        output_callback(error_msg)
                    return ProcessResult(
                        return_code=1,
                        stdout=b"",
                        stderr=error_msg.encode(),
                        error=error_msg,
                    )

                async for progress in progress_generator:
                    if progress.get("type") == "log":
                        log_line = f"[{progress['stream']}] {progress['message']}"
                        if output_callback:
                            output_callback(log_line)

                    elif progress.get("type") == "error":
                        error_msg = str(progress.get("message", "Unknown error"))
                        logger.error(f"Cloud sync error: {error_msg}")
                        if output_callback:
                            output_callback(f"Cloud sync error: {error_msg}")
                        return ProcessResult(
                            return_code=1,
                            stdout=b"",
                            stderr=error_msg.encode(),
                            error=error_msg,
                        )

                    elif progress.get("type") == "completed":
                        if progress["status"] == "success":
                            logger.info("Cloud sync completed successfully")
                            if output_callback:
                                output_callback("Cloud sync completed successfully")
                            return ProcessResult(
                                return_code=0,
                                stdout=b"Cloud sync completed successfully",
                                stderr=b"",
                                error=None,
                            )
                        else:
                            error_msg = "Cloud sync failed"
                            logger.error(f"{error_msg}")
                            if output_callback:
                                output_callback(f"{error_msg}")
                            return ProcessResult(
                                return_code=1,
                                stdout=b"",
                                stderr=error_msg.encode(),
                                error=error_msg,
                            )

                logger.info("Cloud sync completed")
                if output_callback:
                    output_callback("Cloud sync completed")
                return ProcessResult(
                    return_code=0,
                    stdout=b"Cloud sync completed",
                    stderr=b"",
                    error=None,
                )

        except Exception as e:
            logger.error(f"Exception in cloud sync task: {str(e)}")
            if output_callback:
                output_callback(f"Exception in cloud sync task: {str(e)}")
            return ProcessResult(
                return_code=-1, stdout=b"", stderr=str(e).encode(), error=str(e)
            )
