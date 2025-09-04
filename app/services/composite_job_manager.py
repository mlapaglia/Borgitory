import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from collections import deque

from app.models.database import Repository, Job, JobTask, get_db, Schedule
from app.models.enums import JobType
from app.services.rclone_service import rclone_service

logger = logging.getLogger(__name__)


@dataclass
class CompositeJobTaskInfo:
    task_type: str  # 'backup', 'cloud_sync'
    task_name: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_lines: deque = field(default_factory=lambda: deque(maxlen=1000))
    error: Optional[str] = None
    return_code: Optional[int] = None
    # Backup-specific parameters
    source_path: Optional[str] = None
    compression: Optional[str] = None
    dry_run: Optional[bool] = None
    # Prune-specific parameters
    keep_within: Optional[str] = None
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
    show_stats: Optional[bool] = None
    show_list: Optional[bool] = None
    save_space: Optional[bool] = None
    force_prune: Optional[bool] = None
    # Check-specific parameters
    check_type: Optional[str] = None
    verify_data: Optional[bool] = None
    repair_mode: Optional[bool] = None
    max_duration: Optional[int] = None
    archive_prefix: Optional[str] = None
    archive_glob: Optional[str] = None
    first_n_archives: Optional[int] = None
    last_n_archives: Optional[int] = None


@dataclass
class CompositeJobInfo:
    id: str
    db_job_id: int
    job_type: str  # 'scheduled_backup', 'manual_backup'
    status: str = "pending"
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tasks: List[CompositeJobTaskInfo] = field(default_factory=list)
    current_task_index: int = 0
    repository: Optional["Repository"] = None
    schedule: Optional["Schedule"] = None


class CompositeJobManager:
    def __init__(self):
        self.jobs: Dict[str, CompositeJobInfo] = {}
        self._event_queues: List[asyncio.Queue] = []  # For SSE streaming

    async def create_composite_job(
        self,
        job_type: JobType,
        task_definitions: List[Dict],
        repository: Repository,
        schedule: Optional[Schedule] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a new composite job with multiple tasks"""

        job_id = str(uuid.uuid4())

        # Create database job record
        db = next(get_db())
        try:
            db_job = Job(
                repository_id=repository.id,
                job_uuid=job_id,
                type=str(job_type),
                status="pending",
                job_type="composite",
                total_tasks=len(task_definitions),
                completed_tasks=0,
                cloud_sync_config_id=cloud_sync_config_id,
                started_at=datetime.now(),
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)

            # Create task records
            for i, task_def in enumerate(task_definitions):
                task = JobTask(
                    job_id=db_job.id,
                    task_type=task_def["type"],
                    task_name=task_def["name"],
                    status="pending",
                    task_order=i,
                )
                db.add(task)

            db.commit()

            logger.info(
                f"📝 Created composite job {job_id} (db_id: {db_job.id}) with {len(task_definitions)} tasks"
            )

        except Exception as e:
            logger.error(f"Failed to create database job: {e}")
            raise
        finally:
            db.close()

        # Create in-memory job info
        composite_job = CompositeJobInfo(
            id=job_id,
            db_job_id=db_job.id,
            job_type=str(job_type),
            repository=repository,
            schedule=schedule,
        )

        # Create task info objects
        for task_def in task_definitions:
            task_info = CompositeJobTaskInfo(
                task_type=task_def["type"],
                task_name=task_def["name"],
                source_path=task_def.get("source_path"),
                compression=task_def.get("compression"),
                dry_run=task_def.get("dry_run"),
                # Prune parameters
                keep_within=task_def.get("keep_within"),
                keep_daily=task_def.get("keep_daily"),
                keep_weekly=task_def.get("keep_weekly"),
                keep_monthly=task_def.get("keep_monthly"),
                keep_yearly=task_def.get("keep_yearly"),
                show_stats=task_def.get("show_stats"),
                show_list=task_def.get("show_list"),
                save_space=task_def.get("save_space"),
                force_prune=task_def.get("force_prune"),
            )
            composite_job.tasks.append(task_info)

        self.jobs[job_id] = composite_job

        # Start executing the job
        asyncio.create_task(self._execute_composite_job(job_id))

        return job_id

    async def _execute_composite_job(self, job_id: str):
        """Execute all tasks in a composite job sequentially"""
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        logger.info(f"🚀 Starting composite job {job_id} ({job.job_type})")

        job.status = "running"
        self._update_job_status(job_id, "running")

        try:
            # Execute each task sequentially
            for i, task in enumerate(job.tasks):
                job.current_task_index = i

                logger.info(
                    f"🔄 Starting task {i + 1}/{len(job.tasks)}: {task.task_name}"
                )

                task.status = "running"
                task.started_at = datetime.now()
                self._update_task_status(job_id, i, "running")

                try:
                    # Execute the specific task
                    success = await self._execute_task(job, task, i)

                    if success:
                        task.status = "completed"
                        task.completed_at = datetime.now()
                        task.return_code = 0
                        self._update_task_status(job_id, i, "completed", return_code=0)

                        # Update completed tasks count
                        job.completed_tasks = i + 1
                        self._update_job_progress(job_id)

                        logger.info(
                            f"✅ Task {i + 1}/{len(job.tasks)} completed: {task.task_name}"
                        )
                    else:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                        task.return_code = 1
                        self._update_task_status(job_id, i, "failed", return_code=1)

                        logger.error(
                            f"❌ Task {i + 1}/{len(job.tasks)} failed: {task.task_name}"
                        )

                        # Mark all remaining tasks as skipped
                        self._mark_remaining_tasks_as_skipped(job, i + 1)

                        # Fail the entire job if a task fails
                        job.status = "failed"
                        job.completed_at = datetime.now()
                        self._update_job_status(job_id, "failed")
                        return

                except Exception as e:
                    logger.error(f"❌ Exception in task {task.task_name}: {str(e)}")
                    task.status = "failed"
                    task.completed_at = datetime.now()
                    task.return_code = 1
                    task.error = str(e)
                    self._update_task_status(
                        job_id, i, "failed", error=str(e), return_code=1
                    )

                    # Mark all remaining tasks as skipped
                    self._mark_remaining_tasks_as_skipped(job, i + 1)

                    # Fail the entire job
                    job.status = "failed"
                    job.completed_at = datetime.now()
                    self._update_job_status(job_id, "failed")
                    return

            # All tasks completed successfully
            job.status = "completed"
            job.completed_at = datetime.now()
            self._update_job_status(job_id, "completed")

            logger.info(f"🎉 Composite job {job_id} completed successfully")

        except Exception as e:
            logger.error(f"❌ Fatal error in composite job {job_id}: {str(e)}")
            job.status = "failed"
            job.completed_at = datetime.now()
            self._update_job_status(job_id, "failed")

    async def _execute_task(
        self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int
    ) -> bool:
        """Execute a specific task type"""

        if task.task_type == "backup":
            return await self._execute_backup_task(job, task, task_index)
        elif task.task_type == "cloud_sync":
            return await self._execute_cloud_sync_task(job, task, task_index)
        elif task.task_type == "prune":
            return await self._execute_prune_task(job, task, task_index)
        elif task.task_type == "check":
            return await self._execute_check_task(job, task, task_index)
        elif task.task_type == "repo_scan":
            return await self._execute_repo_scan_task(job, task, task_index)
        elif task.task_type == "repo_init":
            return await self._execute_repo_init_task(job, task, task_index)
        elif task.task_type == "repo_list":
            return await self._execute_repo_list_task(job, task, task_index)
        elif task.task_type == "repo_info":
            return await self._execute_repo_info_task(job, task, task_index)
        else:
            logger.error(f"Unknown task type: {task.task_type}")
            return False

    async def _execute_backup_task(
        self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int
    ) -> bool:
        """Execute a borg backup task"""
        try:
            logger.info(f"🔄 Starting borg backup for repository {job.repository.name}")

            # Use the existing borg service to create backup
            # But we'll stream the output to our task instead of creating a separate job
            from app.utils.security import build_secure_borg_command
            from datetime import datetime
            from app.utils.security import validate_compression, validate_archive_name

            # Build the backup command
            compression = "zstd"
            archive_name = f"backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

            validate_compression(compression)
            validate_archive_name(archive_name)

            # Get source path from task or default to /data
            source_path = task.source_path or "/data"
            compression_setting = task.compression or "zstd"

            logger.info(
                f"🔄 Backup settings - Source: {source_path}, Compression: {compression_setting}, Dry run: {task.dry_run}"
            )

            additional_args = [
                "--compression",
                compression_setting,
                "--stats",
                "--progress",
                "--json",
                "--verbose",  # More verbose output
                "--list",  # List files being processed
                f"{job.repository.path}::{archive_name}",
                source_path,
            ]

            # Add dry run flag if requested
            if task.dry_run:
                additional_args.insert(0, "--dry-run")

            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            # Execute the command and capture output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            # Stream output to task
            async for line in process.stdout:
                decoded_line = line.decode("utf-8", errors="replace").rstrip()
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": decoded_line}
                )

                # Broadcast output
                self._broadcast_task_output(job.id, task_index, decoded_line)

            await process.wait()

            if process.returncode == 0:
                logger.info("✅ Backup task completed successfully")
                return True
            else:
                logger.error(
                    f"❌ Backup task failed with return code {process.returncode}"
                )
                task.error = f"Backup failed with return code {process.returncode}"
                return False

        except Exception as e:
            logger.error(f"❌ Exception in backup task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_prune_task(
        self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int
    ) -> bool:
        """Execute a borg prune task to clean up old archives"""
        try:
            logger.info(f"🗑️ Starting borg prune for repository {job.repository.name}")

            from app.utils.security import build_secure_borg_command

            # Build prune command arguments based on task configuration
            additional_args = []

            # Add retention policy arguments
            if hasattr(task, "keep_within") and task.keep_within:
                additional_args.extend(["--keep-within", task.keep_within])

            if hasattr(task, "keep_daily") and task.keep_daily:
                additional_args.extend(["--keep-daily", str(task.keep_daily)])
            if hasattr(task, "keep_weekly") and task.keep_weekly:
                additional_args.extend(["--keep-weekly", str(task.keep_weekly)])
            if hasattr(task, "keep_monthly") and task.keep_monthly:
                additional_args.extend(["--keep-monthly", str(task.keep_monthly)])
            if hasattr(task, "keep_yearly") and task.keep_yearly:
                additional_args.extend(["--keep-yearly", str(task.keep_yearly)])

            # Add common options
            if hasattr(task, "show_stats") and task.show_stats:
                additional_args.append("--stats")
            if hasattr(task, "show_list") and task.show_list:
                additional_args.append("--list")
            if hasattr(task, "save_space") and task.save_space:
                additional_args.append("--save-space")
            if hasattr(task, "force_prune") and task.force_prune:
                additional_args.append("--force")

            # Add dry run flag if requested
            if task.dry_run:
                additional_args.append("--dry-run")

            # Repository path as positional argument
            additional_args.append(job.repository.path)

            logger.info(
                f"🗑️ Prune settings - Repository: {job.repository.path}, Dry run: {task.dry_run}"
            )

            command, env = build_secure_borg_command(
                base_command="borg prune",
                repository_path="",  # Path is in additional_args
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            # Execute the command and capture output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            # Stream output to task
            async for line in process.stdout:
                decoded_line = line.decode("utf-8", errors="replace").rstrip()
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": decoded_line}
                )

                # Broadcast output
                self._broadcast_task_output(job.id, task_index, decoded_line)

            await process.wait()

            if process.returncode == 0:
                logger.info("✅ Prune task completed successfully")
                return True
            else:
                logger.error(
                    f"❌ Prune task failed with return code {process.returncode}"
                )
                task.error = f"Prune failed with return code {process.returncode}"
                return False

        except Exception as e:
            logger.error(f"❌ Exception in prune task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_check_task(
        self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int
    ) -> bool:
        """Execute a borg check task to verify repository integrity"""
        try:
            logger.info(f"🔍 Starting borg check for repository {job.repository.name}")

            from app.utils.security import build_secure_borg_command

            # Build check command arguments based on task configuration
            additional_args = [
                "--verbose",  # Enable verbose output
                "--progress",  # Show progress information
                "--show-rc",  # Show return code information
            ]

            # Determine base command based on check type
            if task.check_type == "repository_only":
                additional_args.append("--repository-only")
            elif task.check_type == "archives_only":
                additional_args.append("--archives-only")
            # For "full", we don't add any flags (default behavior)

            # Add verification options
            if task.verify_data and task.check_type != "repository_only":
                additional_args.append("--verify-data")

            if task.repair_mode:
                additional_args.append("--repair")

            if task.save_space:
                additional_args.append("--save-space")

            # Add time limit for repository-only checks
            if task.max_duration and task.check_type == "repository_only":
                additional_args.extend(["--max-duration", str(task.max_duration)])

            # Add archive filters (only for archive checks)
            if task.check_type != "repository_only":
                if task.archive_prefix:
                    additional_args.extend(["--prefix", task.archive_prefix])

                if task.archive_glob:
                    additional_args.extend(["--glob-archives", task.archive_glob])

                if task.first_n_archives:
                    additional_args.extend(["--first", str(task.first_n_archives)])
                elif task.last_n_archives:
                    additional_args.extend(["--last", str(task.last_n_archives)])

            # Repository path as positional argument
            additional_args.append(job.repository.path)

            logger.info(
                f"🔍 Check settings - Type: {task.check_type}, Repository: {job.repository.path}"
            )

            command, env = build_secure_borg_command(
                base_command="borg check",
                repository_path="",  # Path is in additional_args
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            # Execute the command and capture output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            # Stream output to task
            async for line in process.stdout:
                decoded_line = line.decode("utf-8", errors="replace").rstrip()
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": decoded_line}
                )

                # Broadcast output
                self._broadcast_task_output(job.id, task_index, decoded_line)

            await process.wait()

            if process.returncode == 0:
                logger.info("✅ Check task completed successfully")
                return True
            else:
                logger.error(
                    f"❌ Check task failed with return code {process.returncode}"
                )
                task.error = f"Check failed with return code {process.returncode}"
                return False

        except Exception as e:
            logger.error(f"❌ Exception in check task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_cloud_sync_task(
        self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int
    ) -> bool:
        """Execute a cloud sync task"""
        try:
            if not job.schedule or not job.schedule.cloud_sync_config_id:
                logger.info("📋 No cloud backup configuration - skipping cloud sync")
                task.status = "skipped"
                return True

            logger.info(f"☁️ Starting cloud sync for repository {job.repository.name}")

            # Get cloud backup configuration
            db = next(get_db())
            try:
                from app.models.database import CloudSyncConfig

                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == job.schedule.cloud_sync_config_id)
                    .first()
                )

                if not config or not config.enabled:
                    logger.info(
                        "📋 Cloud backup configuration not found or disabled - skipping"
                    )
                    task.status = "skipped"
                    return True

                # Handle different provider types
                if config.provider == "s3":
                    # Get S3 credentials
                    access_key, secret_key = config.get_credentials()

                    logger.info(
                        f"☁️ Syncing to {config.name} (S3: {config.bucket_name})"
                    )

                    # Use rclone service to sync to S3
                    progress_generator = rclone_service.sync_repository_to_s3(
                        repository=job.repository,
                        access_key_id=access_key,
                        secret_access_key=secret_key,
                        bucket_name=config.bucket_name,
                        path_prefix=config.path_prefix or "",
                    )

                elif config.provider == "sftp":
                    # Get SFTP credentials
                    password, private_key = config.get_sftp_credentials()

                    logger.info(
                        f"☁️ Syncing to {config.name} (SFTP: {config.host}:{config.remote_path})"
                    )

                    # Use rclone service to sync to SFTP
                    progress_generator = rclone_service.sync_repository_to_sftp(
                        repository=job.repository,
                        host=config.host,
                        username=config.username,
                        remote_path=config.remote_path,
                        port=config.port or 22,
                        password=password if password else None,
                        private_key=private_key if private_key else None,
                        path_prefix=config.path_prefix or "",
                    )

                else:
                    logger.error(
                        f"❌ Unsupported cloud backup provider: {config.provider}"
                    )
                    task.error = f"Unsupported provider: {config.provider}"
                    return False

                # Process progress from either S3 or SFTP sync
                async for progress in progress_generator:
                    if progress.get("type") == "log":
                        log_line = f"[{progress['stream']}] {progress['message']}"
                        task.output_lines.append(
                            {"timestamp": datetime.now().isoformat(), "text": log_line}
                        )
                        self._broadcast_task_output(job.id, task_index, log_line)

                    elif progress.get("type") == "error":
                        task.error = progress["message"]
                        logger.error(f"❌ Cloud sync error: {progress['message']}")
                        return False

                    elif progress.get("type") == "completed":
                        if progress["status"] == "success":
                            logger.info("✅ Cloud sync completed successfully")
                            return True
                        else:
                            logger.error("❌ Cloud sync failed")
                            return False

                # If we get here, sync completed without explicit success/failure
                logger.info("✅ Cloud sync completed")
                return True

            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ Exception in cloud sync task: {str(e)}")
            task.error = str(e)
            return False

    def _update_job_status(self, job_id: str, status: str):
        """Update job status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return

            db = next(get_db())
            try:
                db_job = db.query(Job).filter(Job.id == job.db_job_id).first()
                if db_job:
                    db_job.status = status
                    if status == "completed" or status == "failed":
                        db_job.finished_at = datetime.now()
                    db.commit()
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to update job status: {e}")

    def _update_job_progress(self, job_id: str):
        """Update job progress in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return

            db = next(get_db())
            try:
                db_job = db.query(Job).filter(Job.id == job.db_job_id).first()
                if db_job:
                    db_job.completed_tasks = job.completed_tasks
                    db.commit()
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to update job progress: {e}")

    def _update_task_status(
        self,
        job_id: str,
        task_index: int,
        status: str,
        error: str = None,
        return_code: int = None,
    ):
        """Update task status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return

            db = next(get_db())
            try:
                task = (
                    db.query(JobTask)
                    .filter(
                        JobTask.job_id == job.db_job_id,
                        JobTask.task_order == task_index,
                    )
                    .first()
                )

                if task:
                    task.status = status
                    if status == "running":
                        task.started_at = datetime.now()
                    elif status in ["completed", "failed", "skipped"]:
                        task.completed_at = datetime.now()

                        # Store output from in-memory task
                        if task_index < len(job.tasks):
                            task_info = job.tasks[task_index]
                            if task_info.output_lines:
                                task.output = "\n".join(
                                    [line["text"] for line in task_info.output_lines]
                                )

                    if error:
                        task.error = error
                    if return_code is not None:
                        task.return_code = return_code

                    db.commit()
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to update task status: {e}")

    def _broadcast_task_output(self, job_id: str, task_index: int, line: str):
        """Broadcast task output to SSE listeners"""
        event_data = {
            "type": "task_output",
            "job_id": job_id,
            "task_index": task_index,
            "line": line,
            "timestamp": datetime.now().isoformat(),
        }

        for queue in self._event_queues:
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                pass  # Skip if queue is full

    def subscribe_to_events(self) -> asyncio.Queue:
        """Subscribe to job events for SSE streaming"""
        queue = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue

    def unsubscribe_from_events(self, queue: asyncio.Queue):
        """Unsubscribe from job events"""
        if queue in self._event_queues:
            self._event_queues.remove(queue)

    def _mark_remaining_tasks_as_skipped(self, job: CompositeJobInfo, start_index: int):
        """Mark all remaining tasks as skipped when a job fails"""
        for i in range(start_index, len(job.tasks)):
            task = job.tasks[i]
            if task.status == "pending":
                task.status = "skipped"
                task.completed_at = datetime.now()
                self._update_task_status(job.id, i, "skipped")
                logger.info(
                    f"⏭️ Task {i + 1}/{len(job.tasks)} skipped: {task.task_name}"
                )


# Global composite job manager instance
composite_job_manager = CompositeJobManager()
