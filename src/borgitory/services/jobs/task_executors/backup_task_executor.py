"""
Backup Task Executor - Handles backup task execution
"""

import asyncio
import logging
from typing import Optional, Callable, Dict
from borgitory.models.database import Repository
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import cleanup_temp_keyfile
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum
from borgitory.services.borg_service import BorgService


logger = logging.getLogger(__name__)


class BackupTaskExecutor:
    """Handles backup task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        borg_service: BorgService,
    ):
        self.borg_service = borg_service
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    async def execute_backup_task(
        self, job: BorgJob, task: BorgJobTask, repository: Repository
    ) -> bool:
        """Execute a backup task using JobExecutor"""
        try:
            params = task.parameters

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)

                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": line,
                        "progress": None,
                        "task_index": job.current_task_index,
                    },
                )

            # Build backup command
            source_path = params.get("source_path")
            archive_name = params.get(
                "archive_name", f"backup-{now_utc().strftime('%Y%m%d-%H%M%S')}"
            )

            logger.info(
                f"Backup task parameters - source_path: {source_path}, archive_name: {archive_name}"
            )
            logger.info(f"All task parameters: {params}")

            additional_args = []
            additional_args.extend(["--stats", "--list"])
            additional_args.extend(["--filter", "AME"])

            patterns = params.get("patterns", [])
            if patterns and isinstance(patterns, list):
                for pattern in patterns:
                    pattern_arg = f"--pattern={pattern}"
                    additional_args.append(pattern_arg)
                    task_output_callback(f"Added pattern: {pattern_arg}")
                    logger.info(f"Added Borg pattern: {pattern_arg}")

            dry_run = params.get("dry_run", False)
            if dry_run:
                additional_args.append("--dry-run")

            additional_args.append(f"{repository.path}::{archive_name}")

            if source_path:
                additional_args.append(str(source_path))

            logger.info(f"Final additional_args for Borg command: {additional_args}")

            ignore_lock = params.get("ignore_lock", False)
            if ignore_lock:
                logger.info(f"Running borg break-lock on repository: {repository.path}")
                try:
                    await self._execute_break_lock(
                        repository,
                        task_output_callback,
                    )
                except Exception as e:
                    logger.warning(f"Break-lock failed, continuing with backup: {e}")
                    task_output_callback(f"Warning: Break-lock failed: {e}")

            # Prepare environment overrides for cache directory
            env_overrides: dict[str, str] = {}
            if repository.cache_dir:
                env_overrides["BORG_CACHE_DIR"] = repository.cache_dir

            async with self.borg_service.create_borg_command(
                base_command="borg create",
                repository=repository,
                additional_args=additional_args,
                environment_overrides=env_overrides,
                cleanup_keyfile=False,
            ) as (command, env, _):
                process = await self.job_executor.start_process(command, env)

            # Monitor the process (outside context manager since it's long-running)
            result = await self.job_executor.monitor_process_output(
                process, output_callback=task_output_callback
            )

            logger.info(
                f"Backup process completed with return code: {result.return_code}"
            )
            if result.stdout:
                logger.info(f"Backup process stdout length: {len(result.stdout)} bytes")
            if result.stderr:
                logger.info(f"Backup process stderr length: {len(result.stderr)} bytes")
            if result.error:
                logger.error(f"Backup process error: {result.error}")

            task.return_code = result.return_code
            task.status = (
                TaskStatusEnum.COMPLETED
                if result.return_code == 0
                else TaskStatusEnum.FAILED
            )
            task.completed_at = now_utc()

            if hasattr(task, "_temp_keyfile_path"):
                cleanup_temp_keyfile(getattr(task, "_temp_keyfile_path"))
                delattr(task, "_temp_keyfile_path")

            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output and result.return_code != 0:
                    for line in full_output.split("\n"):
                        if line.strip():
                            task.output_lines.append(line)
                            asyncio.create_task(
                                self.output_manager.add_output_line(
                                    job.id, line, "stdout", {}
                                )
                            )

            if result.error:
                task.error = result.error
            elif result.return_code != 0:
                if result.stdout:
                    output_text = result.stdout.decode(
                        "utf-8", errors="replace"
                    ).strip()
                    # Get the last few lines which likely contain the error
                    error_lines = output_text.split("\n")[-5:] if output_text else []
                    stderr_text = (
                        "\n".join(error_lines) if error_lines else "No output captured"
                    )
                else:
                    stderr_text = "No output captured"
                task.error = f"Backup failed with return code {result.return_code}: {stderr_text}"

            return bool(result.return_code == 0)

        except Exception as e:
            logger.error(f"Exception in backup task execution: {str(e)}")
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = f"Backup task failed: {str(e)}"
            task.completed_at = now_utc()

            if hasattr(task, "_temp_keyfile_path"):
                cleanup_temp_keyfile(getattr(task, "_temp_keyfile_path"))
                delattr(task, "_temp_keyfile_path")

            return False

    async def _execute_break_lock(
        self,
        repository: Repository,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Execute borg break-lock command to release stale repository locks"""
        try:
            if output_callback:
                output_callback(
                    "Running 'borg break-lock' to remove stale repository locks..."
                )

            async with self.borg_service.create_borg_command(
                base_command="borg break-lock",
                repository=repository,
                additional_args=[],
            ) as (command, env, _):
                process = await self.job_executor.start_process(command, env)

                try:
                    result = await asyncio.wait_for(
                        self.job_executor.monitor_process_output(
                            process, output_callback=output_callback
                        ),
                        timeout=30,
                    )
                except asyncio.TimeoutError:
                    if output_callback:
                        output_callback("Break-lock timed out, terminating process")
                    process.kill()
                    await process.wait()
                    raise Exception("Break-lock operation timed out")

                if result.return_code == 0:
                    if output_callback:
                        output_callback("Successfully released repository lock")
                    logger.info(
                        f"Successfully released lock on repository: {repository.path}"
                    )
                else:
                    error_msg = f"Break-lock returned {result.return_code}"
                    if result.stdout:
                        stdout_text = result.stdout.decode(
                            "utf-8", errors="replace"
                        ).strip()
                        if stdout_text:
                            error_msg += f": {stdout_text}"

                    if output_callback:
                        output_callback(f"Warning: {error_msg}")
                    logger.warning(
                        f"Break-lock warning for {repository.path}: {error_msg}"
                    )

        except Exception as e:
            error_msg = f"Error executing break-lock: {str(e)}"
            if output_callback:
                output_callback(f"Warning: {error_msg}")
            logger.error(f"Break-lock error for repository {repository.path}: {e}")
            raise

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data by ID - this will be injected by the job manager"""
        # This method will be overridden by the job manager
        return None
