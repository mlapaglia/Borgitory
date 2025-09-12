"""
Modular Borg Job Manager - Refactored for better testability and maintainability

This is the new modular version that uses dependency injection and separate modules
for different concerns (execution, output, queuing, events, database, cloud backup).
"""

import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Dict, Optional, List, AsyncGenerator, Any, TYPE_CHECKING
from dataclasses import dataclass, field

from app.services.job_manager_dependencies import (
    JobManagerConfig,
    JobManagerDependencies,
    get_default_job_manager_dependencies,
)
from app.services.job_queue_manager import JobPriority
from app.services.job_event_broadcaster import EventType
from app.services.job_database_manager import DatabaseJobData

if TYPE_CHECKING:
    from app.models.database import Repository, Schedule

logger = logging.getLogger(__name__)


@dataclass
class BorgJobTask:
    """Individual task within a job"""

    task_type: str  # 'backup', 'prune', 'check', 'cloud_sync'
    task_name: str
    status: str = "pending"  # 'pending', 'running', 'completed', 'failed', 'skipped'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    parameters: Dict = field(default_factory=dict)
    output_lines: List = field(default_factory=list)  # Store task output


@dataclass
class BorgJob:
    """Represents a job in the manager"""

    id: str
    status: str  # 'pending', 'queued', 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None

    # For backward compatibility - single command jobs
    command: Optional[List[str]] = None

    # Multi-task job support
    job_type: str = "simple"  # 'simple' or 'composite'
    tasks: List[BorgJobTask] = field(default_factory=list)
    current_task_index: int = 0

    # Repository context
    repository_id: Optional[int] = None
    schedule: Optional["Schedule"] = None

    # Configuration IDs for composite jobs
    cloud_sync_config_id: Optional[int] = None

    def get_current_task(self) -> Optional[BorgJobTask]:
        """Get the currently executing task (for composite jobs)"""
        if self.job_type == "composite" and 0 <= self.current_task_index < len(
            self.tasks
        ):
            return self.tasks[self.current_task_index]
        return None

    def is_composite(self) -> bool:
        """Check if this is a multi-task composite job"""
        return self.job_type == "composite" and len(self.tasks) > 0


class ModularBorgJobManager:
    """
    Modular Borg Job Manager using dependency injection and separate modules
    """

    def __init__(
        self,
        config: Optional[JobManagerConfig] = None,
        dependencies: Optional[JobManagerDependencies] = None,
    ):
        self.config = config or JobManagerConfig()

        # Initialize dependencies
        if dependencies is None:
            dependencies = get_default_job_manager_dependencies()

        self.dependencies = dependencies

        # Core modules
        self.executor = dependencies.job_executor
        self.output_manager = dependencies.output_manager
        self.queue_manager = dependencies.queue_manager
        self.event_broadcaster = dependencies.event_broadcaster
        self.database_manager = dependencies.database_manager
        self.cloud_coordinator = dependencies.cloud_coordinator

        # Job tracking
        self.jobs: Dict[str, BorgJob] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

        # State management
        self._initialized = False
        self._shutdown_requested = False

        # Set up callbacks
        self._setup_callbacks()

    def _setup_callbacks(self):
        """Set up callbacks between modules"""
        if self.queue_manager:
            self.queue_manager.set_callbacks(
                job_start_callback=self._on_job_start,
                job_complete_callback=self._on_job_complete,
            )

    async def initialize(self):
        """Initialize all modules"""
        if self._initialized:
            return

        # Initialize all modules
        if self.queue_manager:
            await self.queue_manager.initialize()

        if self.event_broadcaster:
            await self.event_broadcaster.initialize()

        self._initialized = True
        logger.info("Modular job manager initialized successfully")

    async def start_borg_command(
        self, command: List[str], env: Optional[Dict] = None, is_backup: bool = False
    ) -> str:
        """Start a Borg command (backward compatibility interface)"""
        await self.initialize()

        job_id = str(uuid.uuid4())

        # Create job
        job = BorgJob(
            id=job_id,
            command=command,
            job_type="simple",
            status="queued" if is_backup else "running",
            started_at=datetime.now(UTC),
        )
        self.jobs[job_id] = job

        # Create output container
        self.output_manager.create_job_output(job_id)

        if is_backup:
            # Queue backup job
            await self.queue_manager.enqueue_job(
                job_id=job_id, job_type="backup", priority=JobPriority.NORMAL
            )
        else:
            # Execute immediately for non-backup jobs
            await self._execute_simple_job(job, command, env)

        # Broadcast job started event
        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"command": " ".join(command[:3]) + "...", "is_backup": is_backup},
        )

        return job_id

    async def _execute_simple_job(
        self, job: BorgJob, command: List[str], env: Optional[Dict] = None
    ):
        """Execute a simple single-command job"""
        job.status = "running"

        try:
            # Start process
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            # Monitor output
            def output_callback(line: str, progress: Dict):
                # Add to output manager
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                # Broadcast output
                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": progress},
                )

            # Execute and monitor
            result = await self.executor.monitor_process_output(
                process, output_callback=output_callback
            )

            # Update job with results
            job.status = "completed" if result.return_code == 0 else "failed"
            job.return_code = result.return_code
            job.completed_at = datetime.now(UTC)

            if result.error:
                job.error = result.error

            # Broadcast completion
            self.event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(UTC)
            logger.error(f"Job {job.id} execution failed: {e}")

            self.event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

        finally:
            # Clean up process
            if job.id in self._processes:
                del self._processes[job.id]

            # Schedule auto cleanup
            asyncio.create_task(
                self._auto_cleanup_job(job.id, self.config.auto_cleanup_delay_seconds)
            )

    def _on_job_start(self, job_id: str, queued_job):
        """Callback when queue manager starts a job"""
        job = self.jobs.get(job_id)
        if job and job.command:
            # Start executing the job
            asyncio.create_task(self._execute_simple_job(job, job.command))

    def _on_job_complete(self, job_id: str, success: bool):
        """Callback when queue manager completes a job"""
        job = self.jobs.get(job_id)
        if job:
            logger.info(f"Job {job_id} completed with success={success}")

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List[Dict],
        repository: "Repository",
        schedule: Optional["Schedule"] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a composite job with multiple tasks"""
        await self.initialize()

        job_id = str(uuid.uuid4())

        # Create tasks
        tasks = []
        for task_def in task_definitions:
            task = BorgJobTask(
                task_type=task_def["type"],
                task_name=task_def["name"],
                parameters=task_def,
            )
            tasks.append(task)

        # Create job
        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="pending",
            started_at=datetime.now(UTC),
            tasks=tasks,
            repository_id=repository.id,
            schedule=schedule,
            cloud_sync_config_id=cloud_sync_config_id,
        )
        self.jobs[job_id] = job

        # Create database record
        if self.database_manager:
            db_job_data = DatabaseJobData(
                job_uuid=job_id,
                repository_id=repository.id,
                job_type=job_type,
                status="pending",
                started_at=job.started_at,
                cloud_sync_config_id=cloud_sync_config_id,
            )
            # Create database job record (UUID is already set as job.id)
            await self.database_manager.create_database_job(db_job_data)

            # Save all tasks to database before starting execution
            # This ensures task structure exists even if job is interrupted
            try:
                await self.database_manager.save_job_tasks(job_id, job.tasks)
                logger.info(f"Pre-saved {len(job.tasks)} tasks for job {job_id}")
            except Exception as e:
                logger.error(f"Failed to pre-save tasks for job {job_id}: {e}")

        # Create output container
        self.output_manager.create_job_output(job_id)

        # Start executing composite job
        asyncio.create_task(self._execute_composite_job(job))

        # Broadcast job started
        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"job_type": job_type, "task_count": len(tasks)},
        )

        return job_id

    async def _execute_composite_job(self, job: BorgJob):
        """Execute a composite job with multiple tasks"""
        job.status = "running"

        # Track if critical tasks have failed to determine notification behavior
        critical_tasks_failed = False
        
        # Log task information for debugging
        task_summary = [f"{task.task_type}:{task.task_name}" for task in job.tasks]
        logger.info(f"📋 Job {job.id} has {len(job.tasks)} tasks: {', '.join(task_summary)}")

        try:
            for i, task in enumerate(job.tasks):
                job.current_task_index = i
                
                # Skip critical tasks if previous critical tasks failed, but allow notification tasks
                if critical_tasks_failed and task.task_type != "notification":
                    task.status = "skipped"
                    task.completed_at = datetime.now(UTC)
                    logger.info(
                        f"⏭️ Task {i + 1}/{len(job.tasks)} skipped: {task.task_name} (due to previous failures)"
                    )
                    continue
                    
                # Log when notification tasks are allowed to proceed despite failures
                if critical_tasks_failed and task.task_type == "notification":
                    logger.info(
                        f"🔔 Task {i + 1}/{len(job.tasks)} proceeding despite failures: {task.task_name} (notification task)"
                    )

                logger.info(
                    f"🔄 Starting task {i + 1}/{len(job.tasks)}: {task.task_name}"
                )
                
                task.status = "running"
                task.started_at = datetime.now(UTC)

                # Broadcast task started
                self.event_broadcaster.broadcast_event(
                    EventType.JOB_PROGRESS,
                    job_id=job.id,
                    data={
                        "task_index": i,
                        "task_name": task.task_name,
                        "task_status": "running",
                    },
                )

                try:
                    # Execute task based on type
                    success = await self._execute_task(job, task, i)

                    task.completed_at = datetime.now(UTC)
                    task.status = "completed" if success else "failed"

                    if success:
                        logger.info(
                            f"✅ Task {i + 1}/{len(job.tasks)} completed: {task.task_name}"
                        )
                    else:
                        logger.error(
                            f"❌ Task {i + 1}/{len(job.tasks)} failed: {task.task_name}"
                        )
                        
                        # Mark critical tasks as failed, but continue for notifications
                        if task.task_type != "notification":
                            critical_tasks_failed = True
                            
                except Exception as e:
                    logger.error(f"❌ Exception in task {task.task_name}: {str(e)}")
                    task.status = "failed"
                    task.completed_at = datetime.now(UTC)
                    task.error = str(e)
                    
                    # Mark critical tasks as failed, but continue for notifications
                    if task.task_type != "notification":
                        critical_tasks_failed = True

            # Determine final job status based on whether critical tasks failed
            if critical_tasks_failed:
                job.status = "failed"
                logger.info(f"💥 Composite job {job.id} completed with failures, but notifications were processed")
            else:
                job.status = "completed"
                logger.info(f"🎉 Composite job {job.id} completed successfully")
                
            job.completed_at = datetime.now(UTC)

            # Update database
            if self.database_manager:
                await self.database_manager.update_job_status(
                    job_uuid=job.id,
                    status=job.status,
                    finished_at=job.completed_at,
                    return_code=0 if job.status == "completed" else 1,
                )

                # Save task details to database
                await self.database_manager.save_job_tasks(job.id, job.tasks)

            # Broadcast completion
            self.event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"status": job.status},
            )

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(UTC)
            logger.error(f"Composite job {job.id} execution failed: {e}")

        finally:
            # Save task details to database (whether successful or failed)
            if self.database_manager:
                try:
                    # Update final job status
                    await self.database_manager.update_job_status(
                        job_uuid=job.id,
                        status=job.status,
                        finished_at=job.completed_at,
                        return_code=0 if job.status == "completed" else 1,
                        error_message=getattr(job, "error", None),
                    )

                    # Save all task details
                    await self.database_manager.save_job_tasks(job.id, job.tasks)
                except Exception as db_e:
                    logger.error(f"Failed to save job data to database: {db_e}")

            # Schedule cleanup
            asyncio.create_task(
                self._auto_cleanup_job(job.id, self.config.auto_cleanup_delay_seconds)
            )

    async def _execute_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a single task within a composite job"""
        try:
            if task.task_type == "backup":
                return await self._execute_backup_task(job, task, task_index)
            elif task.task_type == "prune":
                return await self._execute_prune_task(job, task, task_index)
            elif task.task_type == "check":
                return await self._execute_check_task(job, task, task_index)
            elif task.task_type == "cloud_sync":
                return await self._execute_cloud_sync_task(job, task, task_index)
            elif task.task_type == "notification":
                return await self._execute_notification_task(job, task, task_index)
            else:
                logger.warning(f"Unknown task type: {task.task_type}")
                return False

        except Exception as e:
            task.error = str(e)
            logger.error(f"Task {task.task_name} failed: {e}")
            return False

    async def _execute_backup_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a backup task using job executor"""
        logger.info(f"Executing backup task: {task.task_name}")

        # Get repository data
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            logger.error(f"Repository {job.repository_id} not found")
            task.error = "Repository not found"
            task.return_code = 1
            return False

        # Create output callback for streaming
        async def output_callback(line: str, progress_info: dict):
            # Store output in task
            task.output_lines.append(
                {"timestamp": datetime.now().isoformat(), "text": line}
            )

            # Broadcast to SSE listeners
            await self.output_manager.add_output_line(job.id, line, progress_info=progress_info)
            if self.event_broadcaster:
                from app.services.job_event_broadcaster import EventType

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "task_index": task_index},
                )

        # Build backup command
        from app.utils.security import build_secure_borg_command, validate_compression, validate_archive_name
        from datetime import datetime

        source_path = task.parameters.get("source_path", "/data")
        compression = task.parameters.get("compression", "zstd")
        dry_run = task.parameters.get("dry_run", False)
        
        # Validate parameters
        validate_compression(compression)
        
        # Create archive name
        archive_name = f"backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        validate_archive_name(archive_name)

        additional_args = [
            "--compression", compression,
            "--stats",
            "--progress", 
            "--json",
            "--verbose",
            "--list",
            f"{repo_data['path']}::{archive_name}",
            source_path,
        ]

        if dry_run:
            additional_args.insert(0, "--dry-run")

        command, env = build_secure_borg_command(
            base_command="borg create",
            repository_path="",
            passphrase=repo_data["passphrase"],
            additional_args=additional_args,
        )

        # Execute using job executor's process methods
        try:
            # Start the process
            process = await self.executor.start_process(command, env)
            
            # Monitor output and wait for completion
            result = await self.executor.monitor_process_output(
                process=process,
                output_callback=output_callback,
            )

            if result.return_code == 0:
                task.return_code = 0
                return True
            else:
                task.error = f"Backup failed with return code {result.return_code}"
                task.return_code = result.return_code
                return False

        except Exception as e:
            error_msg = f"Backup task failed: {str(e)}"
            logger.error(error_msg)
            task.error = error_msg
            task.return_code = 1
            return False

    async def _execute_prune_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a prune task using job executor"""
        logger.info(f"Executing prune task: {task.task_name}")

        # Get repository data
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            logger.error(f"Repository {job.repository_id} not found")
            task.error = "Repository not found"
            task.return_code = 1
            return False

        # Create output callback for streaming
        def output_callback(line: str, progress_info: dict):
            # Store output in task
            task.output_lines.append(
                {"timestamp": datetime.now().isoformat(), "text": line}
            )

            # Broadcast to event system if available
            if self.event_broadcaster:
                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": line,
                        "task_index": task_index,
                        "task_type": "prune",
                        "progress_info": progress_info,
                    },
                )

        # Execute prune task using job executor
        try:
            result = await self.executor.execute_prune_task(
                repository_path=repo_data["path"],
                passphrase=repo_data["passphrase"],
                keep_within=task.parameters.get("keep_within"),
                keep_daily=task.parameters.get("keep_daily"),
                keep_weekly=task.parameters.get("keep_weekly"),
                keep_monthly=task.parameters.get("keep_monthly"),
                keep_yearly=task.parameters.get("keep_yearly"),
                show_stats=task.parameters.get("show_stats", True),
                show_list=task.parameters.get("show_list", False),
                save_space=task.parameters.get("save_space", False),
                force_prune=task.parameters.get("force_prune", False),
                dry_run=task.parameters.get("dry_run", False),
                output_callback=output_callback,
            )

            # Store result data
            task.return_code = result.return_code
            if result.error:
                task.error = result.error

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in prune task: {str(e)}")
            task.error = str(e)
            task.return_code = -1
            return False

    async def _execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a check task using job executor"""
        logger.info(f"Executing check task: {task.task_name}")

        # Get repository data
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            logger.error(f"Repository {job.repository_id} not found")
            task.error = "Repository not found"
            task.return_code = 1
            return False

        # Create output callback for streaming
        async def output_callback(line: str, progress_info: dict):
            # Store output in task
            task.output_lines.append(
                {"timestamp": datetime.now().isoformat(), "text": line}
            )

            # Broadcast to SSE listeners
            await self.output_manager.add_output_line(job.id, line, progress_info=progress_info)
            if self.event_broadcaster:
                from app.services.job_event_broadcaster import EventType

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "task_index": task_index},
                )

        # Build check command
        from app.utils.security import build_secure_borg_command

        check_type = task.parameters.get("check_type", "full")
        verify_data = task.parameters.get("verify_data", False)
        repair_mode = task.parameters.get("repair_mode", False)
        save_space = task.parameters.get("save_space", False)
        max_duration = task.parameters.get("max_duration")

        additional_args = [
            "--verbose",
            "--progress",
            "--show-rc",
        ]

        # Add check type specific flags
        if check_type == "repository_only":
            additional_args.append("--repository-only")
        elif check_type == "archives_only":
            additional_args.append("--archives-only")

        # Add verification options
        if verify_data and check_type != "repository_only":
            additional_args.append("--verify-data")

        if repair_mode:
            additional_args.append("--repair")

        if save_space:
            additional_args.append("--save-space")

        if max_duration and check_type == "repository_only":
            additional_args.extend(["--max-duration", str(max_duration)])

        # Add repository path
        additional_args.append(repo_data["path"])

        command, env = build_secure_borg_command(
            base_command="borg check",
            repository_path="",
            passphrase=repo_data["passphrase"],
            additional_args=additional_args,
        )

        # Execute using job executor's process methods
        try:
            # Start the process
            process = await self.executor.start_process(command, env)
            
            # Monitor output and wait for completion
            result = await self.executor.monitor_process_output(
                process=process,
                output_callback=output_callback,
            )

            if result.return_code == 0:
                task.return_code = 0
                return True
            else:
                task.error = f"Check failed with return code {result.return_code}"
                task.return_code = result.return_code
                return False

        except Exception as e:
            error_msg = f"Check task failed: {str(e)}"
            logger.error(error_msg)
            task.error = error_msg
            task.return_code = 1
            return False

    async def _execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a cloud sync task using job executor"""
        logger.info(f"Executing cloud sync task: {task.task_name}")

        # Get repository data
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            logger.error(f"Repository {job.repository_id} not found")
            task.error = "Repository not found"
            task.return_code = 1
            return False

        # Create output callback for streaming
        def output_callback(line: str, progress_info: dict):
            # Store output in task
            task.output_lines.append(
                {"timestamp": datetime.now().isoformat(), "text": line}
            )

            # Broadcast to event system if available
            if self.event_broadcaster:
                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": line,
                        "task_index": task_index,
                        "task_type": "cloud_sync",
                        "progress_info": progress_info,
                    },
                )

        # Execute cloud sync task using job executor
        try:
            result = await self.executor.execute_cloud_sync_task(
                repository_path=repo_data["path"],
                passphrase=repo_data["passphrase"],
                cloud_sync_config_id=job.cloud_sync_config_id,
                output_callback=output_callback,
                db_session_factory=self.database_manager.db_session_factory,
                rclone_service=None,  # Will use default
                http_client_factory=None,  # Will use default
            )

            # Store result data
            task.return_code = result.return_code
            if result.error:
                task.error = result.error

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in cloud sync task: {str(e)}")
            task.error = str(e)
            task.return_code = -1
            return False

    async def _execute_notification_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a notification task"""
        logger.info(f"Executing notification task: {task.task_name}")

        try:
            # Get repository data
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                logger.error(f"Repository {job.repository_id} not found")
                task.error = "Repository not found"
                task.return_code = 1
                return False

            # Get notification configuration
            config_id = task.parameters.get("config_id")
            if not config_id:
                logger.error("No notification configuration ID provided")
                task.error = "No notification configuration"
                task.return_code = 1
                return False

            # Get config from database
            from app.models.database import NotificationConfig
            from app.utils.db_session import get_db_session

            with get_db_session() as db:
                notification_config = (
                    db.query(NotificationConfig)
                    .filter(NotificationConfig.id == config_id)
                    .first()
                )

                if not notification_config or not notification_config.enabled:
                    logger.info("Notification configuration not found or disabled - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                # Determine if we should send notification based on job status
                previous_tasks = job.tasks[:task_index] if task_index > 0 else []
                job_success = all(t.status == "completed" for t in previous_tasks if t.task_type != "notification")
                
                notify_on_success = task.parameters.get("notify_on_success", True)
                notify_on_failure = task.parameters.get("notify_on_failure", True)
                
                should_notify = (
                    job_success and notify_on_success
                ) or (not job_success and notify_on_failure)

                if not should_notify:
                    logger.info("Notification not configured for current job status - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                # Add initial output
                initial_output = f"Sending notification via {notification_config.provider}"
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": initial_output}
                )

                # Send notification based on provider
                if notification_config.provider == "pushover":
                    success = await self._send_pushover_notification(
                        notification_config, job, repo_data, task, job_success
                    )
                else:
                    error_msg = f"Unsupported notification provider: {notification_config.provider}"
                    logger.error(error_msg)
                    task.error = error_msg
                    task.return_code = 1
                    return False

                if success:
                    success_msg = f"Notification sent successfully via {notification_config.provider}"
                    task.output_lines.append(
                        {"timestamp": datetime.now().isoformat(), "text": success_msg}
                    )
                    logger.info(success_msg)
                    task.return_code = 0
                    return True
                else:
                    task.return_code = 1
                    return False

        except Exception as e:
            error_msg = f"Notification task failed: {str(e)}"
            logger.error(error_msg)
            task.error = error_msg
            task.return_code = 1
            return False

    async def _send_pushover_notification(
        self, config, job: BorgJob, repo_data: dict, task: BorgJobTask, job_success: bool
    ) -> bool:
        """Send notification via Pushover"""
        try:
            import httpx
            from app.models.database import get_cipher_suite

            # Decrypt credentials
            cipher_suite = get_cipher_suite()
            user_key = cipher_suite.decrypt(config.encrypted_user_key.encode()).decode()
            app_token = cipher_suite.decrypt(config.encrypted_app_token.encode()).decode()

            # Create message
            status_emoji = "✅" if job_success else "❌"
            status_text = "completed successfully" if job_success else "failed"
            message = f"Backup {status_text} for repository '{repo_data['name']}'"
            title = f"{status_emoji} Borgitory Backup"

            # Send to Pushover API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": app_token,
                        "user": user_key,
                        "title": title,
                        "message": message,
                    },
                )

                if response.status_code == 200:
                    return True
                else:
                    error_msg = f"Pushover API error: {response.status_code} - {response.text}"
                    task.error = error_msg
                    task.output_lines.append(
                        {"timestamp": datetime.now().isoformat(), "text": error_msg}
                    )
                    return False

        except Exception as e:
            error_msg = f"Failed to send Pushover notification: {str(e)}"
            task.error = error_msg
            task.output_lines.append(
                {"timestamp": datetime.now().isoformat(), "text": error_msg}
            )
            return False

    async def _get_repository_data(self, repository_id: int) -> Optional[Dict]:
        """Get repository data from database"""
        if self.database_manager:
            return await self.database_manager.get_repository_data(repository_id)

        # Fallback: direct database access for testing/backward compatibility
        from app.utils.db_session import get_db_session
        from app.models.database import Repository

        with get_db_session() as db:
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                return None

            return {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "passphrase": repository.get_passphrase(),
            }

    # Backward compatibility methods

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get job status (backward compatibility)"""
        job = self.jobs.get(job_id)
        if not job:
            return None

        return {
            "running": job.status == "running",
            "completed": job.status == "completed",
            "status": job.status,
            "started_at": job.started_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "return_code": job.return_code,
            "error": job.error,
        }

    async def get_job_output_stream(self, job_id: str) -> Dict[str, Any]:
        """Get job output stream (backward compatibility)"""
        return await self.output_manager.get_job_output_stream(job_id)

    async def stream_job_output(self, job_id: str) -> AsyncGenerator[Dict, None]:
        """Stream job output (backward compatibility)"""
        async for output in self.output_manager.stream_job_output(job_id, follow=True):
            yield output

    async def stream_all_job_updates(self) -> AsyncGenerator[Dict, None]:
        """Stream all job updates via SSE"""
        async for event in self.event_broadcaster.stream_all_events():
            yield event

    def subscribe_to_events(self) -> asyncio.Queue:
        """Subscribe to job events for SSE streaming"""
        if hasattr(self.event_broadcaster, "subscribe_to_events"):
            return self.event_broadcaster.subscribe_to_events()
        else:
            # Fallback: create a queue and return it
            queue = asyncio.Queue(maxsize=100)
            return queue

    def unsubscribe_from_events(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from job events"""
        if hasattr(self.event_broadcaster, "unsubscribe_from_events"):
            self.event_broadcaster.unsubscribe_from_events(queue)

    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        if self.queue_manager:
            stats = self.queue_manager.get_queue_stats()
            return {
                "max_concurrent_backups": self.config.max_concurrent_backups,
                "running_backups": len(
                    [
                        j
                        for j in self.jobs.values()
                        if j.status == "running" and "backup" in j.job_type
                    ]
                ),
                "queued_backups": stats.queue_size_by_type.get("backup", 0),
                "available_slots": stats.available_slots,
                "queue_size": stats.total_queued,
            }
        return {}

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job from memory"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self.output_manager.clear_job_output(job_id)
            logger.info(f"Cleaned up job {job_id}")
            return True
        return False

    async def _auto_cleanup_job(self, job_id: str, delay: int):
        """Auto-cleanup job after delay"""
        await asyncio.sleep(delay)
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status in ["completed", "failed"]:
                # Ensure task data is persisted before cleanup
                if self.database_manager and hasattr(job, "tasks") and job.tasks:
                    try:
                        await self.database_manager.save_job_tasks(job_id, job.tasks)
                        logger.info(
                            f"Persisted task data for job {job_id} before cleanup"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to persist task data for job {job_id}: {e}"
                        )

                self.cleanup_job(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        process = self._processes.get(job_id)
        if process:
            try:
                await self.executor.terminate_process(process)
                logger.info(f"Cancelled job {job_id}")
                return True
            except Exception as e:
                logger.error(f"Error cancelling job {job_id}: {e}")
                return False
        return False

    async def shutdown(self):
        """Shutdown the job manager and all modules"""
        logger.info("Shutting down modular job manager...")
        self._shutdown_requested = True

        # Cancel all running processes
        for job_id, process in self._processes.items():
            try:
                await self.executor.terminate_process(process)
            except Exception as e:
                logger.error(f"Error terminating job {job_id}: {e}")

        # Shutdown modules
        if self.queue_manager:
            await self.queue_manager.shutdown()

        if self.event_broadcaster:
            await self.event_broadcaster.shutdown()

        if self.cloud_coordinator:
            await self.cloud_coordinator.shutdown()

        # Clear data
        self.jobs.clear()
        self._processes.clear()

        logger.info("Modular job manager shutdown complete")


# Factory pattern and singleton for backward compatibility
_job_manager_instance: Optional[ModularBorgJobManager] = None


def get_job_manager(config=None) -> ModularBorgJobManager:
    """Factory function for job manager with singleton behavior"""
    global _job_manager_instance
    if _job_manager_instance is None:
        if config is None:
            # Use environment variables or defaults
            import os

            internal_config = JobManagerConfig(
                max_concurrent_backups=int(
                    os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")
                ),
                auto_cleanup_delay_seconds=int(
                    os.getenv("BORG_AUTO_CLEANUP_DELAY", "30")
                ),
                max_output_lines_per_job=int(
                    os.getenv("BORG_MAX_OUTPUT_LINES", "1000")
                ),
            )
        elif hasattr(config, "to_internal_config"):
            # Backward compatible config wrapper
            internal_config = config.to_internal_config()
        else:
            # Assume it's already a JobManagerConfig
            internal_config = config

        _job_manager_instance = ModularBorgJobManager(internal_config)
        logger.info(
            f"Created new modular job manager with config: max_concurrent={internal_config.max_concurrent_backups}"
        )

    return _job_manager_instance


def reset_job_manager():
    """Reset job manager for testing"""
    global _job_manager_instance
    if _job_manager_instance:
        logger.warning("Resetting modular job manager instance")
    _job_manager_instance = None


# Backward compatibility aliases
BorgJobManager = ModularBorgJobManager
BorgJobManagerConfig = JobManagerConfig
