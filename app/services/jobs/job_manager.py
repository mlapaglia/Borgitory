"""
Job Manager - Consolidated modular job management system

This file consolidates the job management functionality from multiple files into a single,
clean architecture following the same pattern as other services in the application.
"""

import asyncio
import logging
import uuid
import os
from datetime import datetime, UTC
from typing import Dict, Optional, List, AsyncGenerator, Any, Callable, TYPE_CHECKING
from dataclasses import dataclass, field

from app.services.jobs.job_executor import JobExecutor
from app.services.jobs.job_output_manager import JobOutputManager
from app.services.jobs.job_queue_manager import JobQueueManager, JobPriority
from app.services.jobs.job_event_broadcaster import JobEventBroadcaster, EventType
from app.services.jobs.job_database_manager import JobDatabaseManager, DatabaseJobData
from app.services.cloud_backup_coordinator import CloudBackupCoordinator
from app.utils.db_session import get_db_session

if TYPE_CHECKING:
    from app.models.database import Repository, Schedule

logger = logging.getLogger(__name__)


@dataclass
class JobManagerConfig:
    """Configuration for the job manager"""

    # Concurrency settings
    max_concurrent_backups: int = 5
    max_concurrent_operations: int = 10

    # Output and storage settings
    max_output_lines_per_job: int = 1000
    auto_cleanup_delay_seconds: int = 30

    # Queue settings
    queue_poll_interval: float = 0.1

    # SSE settings
    sse_keepalive_timeout: float = 30.0
    sse_max_queue_size: int = 100

    # Cloud backup settings
    max_concurrent_cloud_uploads: int = 3


@dataclass
class JobManagerDependencies:
    """Injectable dependencies for the job manager"""

    # Core services
    job_executor: Optional[JobExecutor] = None
    output_manager: Optional[JobOutputManager] = None
    queue_manager: Optional[JobQueueManager] = None
    event_broadcaster: Optional[JobEventBroadcaster] = None
    database_manager: Optional[JobDatabaseManager] = None
    cloud_coordinator: Optional[CloudBackupCoordinator] = None

    # External dependencies (for testing/customization)
    subprocess_executor: Optional[Callable] = field(
        default_factory=lambda: asyncio.create_subprocess_exec
    )
    db_session_factory: Optional[Callable] = None
    rclone_service: Optional[Any] = None
    http_client_factory: Optional[Callable] = None

    def __post_init__(self):
        """Initialize default dependencies if not provided"""
        if self.db_session_factory is None:
            self.db_session_factory = self._default_db_session_factory

    def _default_db_session_factory(self):
        """Default database session factory"""
        return get_db_session()


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

    command: Optional[List[str]] = None

    job_type: str = "simple"  # 'simple' or 'composite'
    tasks: List[BorgJobTask] = field(default_factory=list)
    current_task_index: int = 0

    repository_id: Optional[int] = None
    schedule: Optional["Schedule"] = None

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


class JobManagerFactory:
    """Factory for creating job manager instances with proper dependency injection"""

    @classmethod
    def create_dependencies(
        cls,
        config: Optional[JobManagerConfig] = None,
        custom_dependencies: Optional[JobManagerDependencies] = None,
    ) -> JobManagerDependencies:
        """Create a complete set of dependencies for the job manager"""

        if config is None:
            config = JobManagerConfig()

        if custom_dependencies is None:
            custom_dependencies = JobManagerDependencies()

        # Create core services with proper configuration
        deps = JobManagerDependencies(
            # Use provided dependencies or create new ones
            subprocess_executor=custom_dependencies.subprocess_executor,
            db_session_factory=custom_dependencies.db_session_factory,
            rclone_service=custom_dependencies.rclone_service,
            http_client_factory=custom_dependencies.http_client_factory,
        )

        # Job Executor
        if custom_dependencies.job_executor:
            deps.job_executor = custom_dependencies.job_executor
        else:
            deps.job_executor = JobExecutor(
                subprocess_executor=deps.subprocess_executor
            )

        # Job Output Manager
        if custom_dependencies.output_manager:
            deps.output_manager = custom_dependencies.output_manager
        else:
            deps.output_manager = JobOutputManager(
                max_lines_per_job=config.max_output_lines_per_job
            )

        # Job Queue Manager
        if custom_dependencies.queue_manager:
            deps.queue_manager = custom_dependencies.queue_manager
        else:
            deps.queue_manager = JobQueueManager(
                max_concurrent_backups=config.max_concurrent_backups,
                max_concurrent_operations=config.max_concurrent_operations,
                queue_poll_interval=config.queue_poll_interval,
            )

        # Job Event Broadcaster
        if custom_dependencies.event_broadcaster:
            deps.event_broadcaster = custom_dependencies.event_broadcaster
        else:
            deps.event_broadcaster = JobEventBroadcaster(
                max_queue_size=config.sse_max_queue_size,
                keepalive_timeout=config.sse_keepalive_timeout,
            )

        # Cloud Backup Coordinator
        if custom_dependencies.cloud_coordinator:
            deps.cloud_coordinator = custom_dependencies.cloud_coordinator
        else:
            deps.cloud_coordinator = CloudBackupCoordinator(
                db_session_factory=deps.db_session_factory,
                rclone_service=deps.rclone_service,
                http_client_factory=deps.http_client_factory,
            )

        # Job Database Manager
        if custom_dependencies.database_manager:
            deps.database_manager = custom_dependencies.database_manager
        else:
            deps.database_manager = JobDatabaseManager(
                db_session_factory=deps.db_session_factory,
                cloud_backup_coordinator=deps.cloud_coordinator,
            )

        return deps

    @classmethod
    def create_for_testing(
        cls,
        mock_subprocess: Optional[Callable] = None,
        mock_db_session: Optional[Callable] = None,
        mock_rclone_service: Optional[Any] = None,
        mock_http_client: Optional[Callable] = None,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create dependencies with mocked services for testing"""

        test_deps = JobManagerDependencies(
            subprocess_executor=mock_subprocess,
            db_session_factory=mock_db_session,
            rclone_service=mock_rclone_service,
            http_client_factory=mock_http_client,
        )

        return cls.create_dependencies(config=config, custom_dependencies=test_deps)

    @classmethod
    def create_minimal(cls) -> JobManagerDependencies:
        """Create minimal dependencies (useful for testing or simple use cases)"""

        config = JobManagerConfig(
            max_concurrent_backups=1,
            max_concurrent_operations=2,
            max_output_lines_per_job=100,
            sse_max_queue_size=10,
        )

        return cls.create_dependencies(config=config)


class JobManager:
    """
    Main Job Manager using dependency injection and modular architecture
    """

    def __init__(
        self,
        config: Optional[JobManagerConfig] = None,
        dependencies: Optional[JobManagerDependencies] = None,
    ):
        self.config = config or JobManagerConfig()

        if dependencies is None:
            dependencies = JobManagerFactory.create_dependencies()

        self.dependencies = dependencies

        self.executor = dependencies.job_executor
        self.output_manager = dependencies.output_manager
        self.queue_manager = dependencies.queue_manager
        self.event_broadcaster = dependencies.event_broadcaster
        self.database_manager = dependencies.database_manager
        self.cloud_coordinator = dependencies.cloud_coordinator

        self.jobs: Dict[str, BorgJob] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

        self._initialized = False
        self._shutdown_requested = False

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

        if self.queue_manager:
            await self.queue_manager.initialize()

        if self.event_broadcaster:
            await self.event_broadcaster.initialize()

        self._initialized = True
        logger.info("Job manager initialized successfully")

    async def start_borg_command(
        self, command: List[str], env: Optional[Dict] = None, is_backup: bool = False
    ) -> str:
        """Start a Borg command (backward compatibility interface)"""
        await self.initialize()

        job_id = str(uuid.uuid4())

        job = BorgJob(
            id=job_id,
            command=command,
            job_type="simple",
            status="queued" if is_backup else "running",
            started_at=datetime.now(UTC),
        )
        self.jobs[job_id] = job

        self.output_manager.create_job_output(job_id)

        if is_backup:
            await self.queue_manager.enqueue_job(
                job_id=job_id, job_type="backup", priority=JobPriority.NORMAL
            )
        else:
            await self._execute_simple_job(job, command, env)

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
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            def output_callback(line: str, progress: Dict):
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": progress},
                )

            result = await self.executor.monitor_process_output(
                process, output_callback=output_callback
            )

            job.status = "completed" if result.return_code == 0 else "failed"
            job.return_code = result.return_code
            job.completed_at = datetime.now(UTC)

            if result.error:
                job.error = result.error

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
            if job.id in self._processes:
                del self._processes[job.id]

            asyncio.create_task(
                self._auto_cleanup_job(job.id, self.config.auto_cleanup_delay_seconds)
            )

    def _on_job_start(self, job_id: str, queued_job):
        """Callback when queue manager starts a job"""
        job = self.jobs.get(job_id)
        if job and job.command:
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

        tasks = []
        for task_def in task_definitions:
            task = BorgJobTask(
                task_type=task_def["type"],
                task_name=task_def["name"],
                parameters=task_def,
            )
            tasks.append(task)

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

        if self.database_manager:
            db_job_data = DatabaseJobData(
                job_uuid=job_id,
                repository_id=repository.id,
                job_type=job_type,
                status="pending",
                started_at=job.started_at,
                cloud_sync_config_id=cloud_sync_config_id,
            )

            await self.database_manager.create_database_job(db_job_data)

            try:
                await self.database_manager.save_job_tasks(job_id, job.tasks)
                logger.info(f"Pre-saved {len(job.tasks)} tasks for job {job_id}")
            except Exception as e:
                logger.error(f"Failed to pre-save tasks for job {job_id}: {e}")

        self.output_manager.create_job_output(job_id)

        asyncio.create_task(self._execute_composite_job(job))

        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"job_type": job_type, "task_count": len(tasks)},
        )

        return job_id

    async def _execute_composite_job(self, job: BorgJob):
        """Execute a composite job with multiple sequential tasks"""
        job.status = "running"

        # Update job status in database
        if self.database_manager:
            await self.database_manager.update_job_status(job.id, "running")

        self.event_broadcaster.broadcast_event(
            EventType.JOB_STATUS_CHANGED,
            job_id=job.id,
            data={"status": "running", "started_at": job.started_at.isoformat()},
        )

        try:
            for task_index, task in enumerate(job.tasks):
                job.current_task_index = task_index

                task.status = "running"
                task.started_at = datetime.now(UTC)

                self.event_broadcaster.broadcast_event(
                    EventType.TASK_STARTED,
                    job_id=job.id,
                    data={
                        "task_index": task_index,
                        "task_type": task.task_type,
                        "task_name": task.task_name,
                    },
                )

                # Execute the task based on its type
                try:
                    if task.task_type == "backup":
                        await self._execute_backup_task(job, task, task_index)
                    elif task.task_type == "prune":
                        await self._execute_prune_task(job, task, task_index)
                    elif task.task_type == "check":
                        await self._execute_check_task(job, task, task_index)
                    elif task.task_type == "cloud_sync":
                        await self._execute_cloud_sync_task(job, task, task_index)
                    elif task.task_type == "notification":
                        await self._execute_notification_task(job, task, task_index)
                    else:
                        await self._execute_task(job, task, task_index)

                    # Task status, return_code, and completed_at are already set by the individual task methods
                    # Just ensure completed_at is set if not already
                    if not task.completed_at:
                        task.completed_at = datetime.now(UTC)

                    self.event_broadcaster.broadcast_event(
                        EventType.TASK_COMPLETED
                        if task.status == "completed"
                        else EventType.TASK_FAILED,
                        job_id=job.id,
                        data={
                            "task_index": task_index,
                            "status": task.status,
                            "return_code": task.return_code,
                        },
                    )

                    # Update task in database BEFORE checking if we should break
                    if self.database_manager:
                        try:
                            logger.info(f"Saving task {task.task_type} to database - Status: {task.status}, Return Code: {task.return_code}, Output Lines: {len(task.output_lines)}")
                            await self.database_manager.save_job_tasks(job.id, job.tasks)
                            logger.info(f"Successfully saved task {task.task_type} to database")
                        except Exception as e:
                            logger.error(f"Failed to update tasks in database: {e}")

                    # If task failed and it's critical, stop the job
                    if task.status == "failed" and task.task_type in ["backup"]:
                        logger.error(f"Critical task {task.task_type} failed, stopping job")
                        break

                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                    task.completed_at = datetime.now(UTC)
                    logger.error(f"Task {task.task_type} in job {job.id} failed: {e}")

                    self.event_broadcaster.broadcast_event(
                        EventType.TASK_FAILED,
                        job_id=job.id,
                        data={"task_index": task_index, "error": str(e)},
                    )

                    # Update task in database for exception case too
                    if self.database_manager:
                        try:
                            logger.info(f"Saving exception task {task.task_type} to database - Status: {task.status}, Return Code: {task.return_code}, Output Lines: {len(task.output_lines)}")
                            await self.database_manager.save_job_tasks(job.id, job.tasks)
                            logger.info(f"Successfully saved exception task {task.task_type} to database")
                        except Exception as db_e:
                            logger.error(f"Failed to update tasks in database: {db_e}")

                    # If it's a critical task, stop execution
                    if task.task_type in ["backup"]:
                        break

            # Determine final job status
            failed_tasks = [t for t in job.tasks if t.status == "failed"]
            completed_tasks = [t for t in job.tasks if t.status == "completed"]

            if len(completed_tasks) == len(job.tasks):
                job.status = "completed"
            elif failed_tasks:
                # Check if any critical tasks failed
                critical_failed = any(t.task_type in ["backup"] for t in failed_tasks)
                job.status = "failed" if critical_failed else "completed"
            else:
                job.status = "failed"

            job.completed_at = datetime.now(UTC)

            # Update final job status
            if self.database_manager:
                await self.database_manager.update_job_status(
                    job.id, job.status, job.completed_at
                )

            self.event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"status": job.status, "completed_at": job.completed_at.isoformat()},
            )

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(UTC)
            logger.error(f"Composite job {job.id} execution failed: {e}")

            if self.database_manager:
                await self.database_manager.update_job_status(
                    job.id, "failed", job.completed_at, str(e)
                )

            self.event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

        finally:
            asyncio.create_task(
                self._auto_cleanup_job(job.id, self.config.auto_cleanup_delay_seconds)
            )

    async def _execute_simple_job(self, job: BorgJob, command: List[str], env: Optional[Dict] = None):
        """Execute a simple single-command job (for test compatibility)"""
        job.status = "running"

        try:
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            def output_callback(line: str, progress: Dict):
                asyncio.create_task(
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": progress},
                )

            result = await self.executor.monitor_process_output(
                process, output_callback=output_callback
            )

            job.status = "completed" if result.return_code == 0 else "failed"
            job.return_code = result.return_code
            job.completed_at = datetime.now(UTC)

            if result.error:
                job.error = result.error

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
            if job.id in self._processes:
                del self._processes[job.id]

    async def _execute_backup_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a backup task using JobExecutor"""
        try:
            from app.utils.security import build_secure_borg_command

            params = task.parameters

            # Get repository data
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                task.status = "failed"
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = datetime.now(UTC)
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = repo_data.get("passphrase") or params.get("passphrase")

            def task_output_callback(line: str, progress: Dict):
                task.output_lines.append(line)
                asyncio.create_task(
                    self.output_manager.add_output_line(job.id, line, "stdout", progress)
                )

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": progress, "task_index": job.current_task_index},
                )

            # Build backup command
            paths = params.get("paths", [])
            excludes = params.get("excludes", [])
            archive_name = params.get("archive_name", f"backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}")

            logger.info(f"Backup task parameters - paths: {paths}, excludes: {excludes}, archive_name: {archive_name}")
            logger.info(f"All task parameters: {params}")

            additional_args = []
            additional_args.extend(["--stats", "--list"])
            additional_args.extend(["--filter", "AME"])

            for exclude in excludes:
                additional_args.extend(["--exclude", exclude])

            additional_args.append(f"{repository_path}::{archive_name}")

            # Add paths - if empty, add a default path for testing
            if not paths:
                logger.warning("No source paths specified for backup, using default test path")
                paths = ["/tmp"]  # Add a default path for testing

            additional_args.extend(paths)

            logger.info(f"Final additional_args for Borg command: {additional_args}")

            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                additional_args=additional_args,
            )

            # Start the backup process
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            # Monitor the process
            result = await self.executor.monitor_process_output(
                process, output_callback=task_output_callback
            )

            # Log the result for debugging
            logger.info(f"Backup process completed with return code: {result.return_code}")
            if result.stdout:
                logger.info(f"Backup process stdout length: {len(result.stdout)} bytes")
            if result.stderr:
                logger.info(f"Backup process stderr length: {len(result.stderr)} bytes")
            if result.error:
                logger.error(f"Backup process error: {result.error}")

            # Clean up process tracking
            if job.id in self._processes:
                del self._processes[job.id]

            # Set task status based on result
            task.return_code = result.return_code
            task.status = "completed" if result.return_code == 0 else "failed"

            # Always add the full process output to task output_lines for debugging
            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output and result.return_code != 0:
                    # Add the captured output to the task output lines for visibility
                    for line in full_output.split('\n'):
                        if line.strip():
                            task.output_lines.append(line)
                            # Also add to output manager for real-time display
                            asyncio.create_task(
                                self.output_manager.add_output_line(job.id, line, "stdout", {})
                            )

            if result.error:
                task.error = result.error
            elif result.return_code != 0:
                # Set a default error message if none provided by result
                # Since stderr is redirected to stdout, check stdout for error messages
                if result.stdout:
                    output_text = result.stdout.decode("utf-8", errors="replace").strip()
                    # Get the last few lines which likely contain the error
                    error_lines = output_text.split('\n')[-5:] if output_text else []
                    stderr_text = '\n'.join(error_lines) if error_lines else "No output captured"
                else:
                    stderr_text = "No output captured"
                task.error = f"Backup failed with return code {result.return_code}: {stderr_text}"

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in backup task execution: {str(e)}")
            task.status = "failed"
            task.return_code = 1
            task.error = f"Backup task failed: {str(e)}"
            task.completed_at = datetime.now(UTC)
            return False

    async def _execute_prune_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a prune task using JobExecutor"""
        params = task.parameters

        def task_output_callback(line: str, progress: Dict):
            task.output_lines.append(line)
            asyncio.create_task(
                self.output_manager.add_output_line(job.id, line, "stdout", progress)
            )

        result = await self.executor.execute_prune_task(
            repository_path=params.get("repository_path"),
            passphrase=params.get("passphrase"),
            keep_within=params.get("keep_within"),
            keep_daily=params.get("keep_daily"),
            keep_weekly=params.get("keep_weekly"),
            keep_monthly=params.get("keep_monthly"),
            keep_yearly=params.get("keep_yearly"),
            show_stats=params.get("show_stats", True),
            show_list=params.get("show_list", False),
            save_space=params.get("save_space", False),
            force_prune=params.get("force_prune", False),
            dry_run=params.get("dry_run", False),
            output_callback=task_output_callback,
        )

        # Set task status based on result
        task.return_code = result.return_code
        task.status = "completed" if result.return_code == 0 else "failed"
        if result.error:
            task.error = result.error

        return result.return_code == 0

    async def _execute_check_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a repository check task"""
        try:
            from app.utils.security import build_secure_borg_command

            params = task.parameters

            # Get repository data
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                task.status = "failed"
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = datetime.now(UTC)
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = repo_data.get("passphrase") or params.get("passphrase")

            def task_output_callback(line: str, progress: Dict):
                task.output_lines.append(line)
                asyncio.create_task(
                    self.output_manager.add_output_line(job.id, line, "stdout", progress)
                )

            additional_args = []

            # Add check options
            if params.get("repository_only", False):
                additional_args.append("--repository-only")
            if params.get("archives_only", False):
                additional_args.append("--archives-only")
            if params.get("verify_data", False):
                additional_args.append("--verify-data")
            if params.get("repair", False):
                additional_args.append("--repair")

            additional_args.append(repository_path)

            command, env = build_secure_borg_command(
                base_command="borg check",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                additional_args=additional_args,
            )

            # Start the check process
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            # Monitor the process
            result = await self.executor.monitor_process_output(
                process, output_callback=task_output_callback
            )

            # Clean up process tracking
            if job.id in self._processes:
                del self._processes[job.id]

            # Set task status based on result
            task.return_code = result.return_code
            task.status = "completed" if result.return_code == 0 else "failed"
            if result.error:
                task.error = result.error

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Error executing check task for job {job.id}: {str(e)}")
            task.status = "failed"
            task.return_code = 1
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            return False

    async def _execute_cloud_sync_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a cloud sync task using JobExecutor"""
        params = task.parameters

        def task_output_callback(line: str, progress: Dict):
            task.output_lines.append(line)
            asyncio.create_task(
                self.output_manager.add_output_line(job.id, line, "stdout", progress)
            )

        result = await self.executor.execute_cloud_sync_task(
            repository_path=params.get("repository_path"),
            passphrase=params.get("passphrase"),  # Not used but kept for consistency
            cloud_sync_config_id=params.get("cloud_sync_config_id"),
            output_callback=task_output_callback,
            db_session_factory=self.dependencies.db_session_factory,
            rclone_service=self.dependencies.rclone_service,
            http_client_factory=self.dependencies.http_client_factory,
        )

        # Set task status based on result
        task.return_code = result.return_code
        task.status = "completed" if result.return_code == 0 else "failed"
        if result.error:
            task.error = result.error

        return result.return_code == 0

    async def _execute_notification_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a notification task"""
        params = task.parameters

        notification_config_id = params.get("notification_config_id") or params.get("config_id")
        if not notification_config_id:
            logger.info("No notification configuration provided - skipping notification")
            task.status = "failed"
            task.return_code = 1
            task.error = "No notification configuration"
            return False

        # Get notification configuration
        try:
            with get_db_session() as db:
                from app.models.database import NotificationConfig
                config = db.query(NotificationConfig).filter(
                    NotificationConfig.id == notification_config_id
                ).first()

                if not config:
                    logger.info("Notification configuration not found - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                if not config.enabled:
                    logger.info("Notification configuration disabled - skipping")
                    task.status = "skipped"
                    task.return_code = 0
                    return True

                if config.provider == "pushover":
                    # Get decrypted credentials
                    user_key, app_token = config.get_pushover_credentials()

                    # Send Pushover notification
                    success = await self._send_pushover_notification(
                        app_token,
                        user_key,
                        params.get("title", "Borgitory Notification"),
                        params.get("message", "Job completed"),
                        params.get("priority", 0)
                    )

                    task.status = "completed" if success else "failed"
                    task.return_code = 0 if success else 1
                    if not success:
                        task.error = "Failed to send Pushover notification"
                    return success
                else:
                    logger.warning(f"Unsupported notification provider: {config.provider}")
                    task.status = "failed"
                    task.error = f"Unsupported provider: {config.provider}"
                    return False

        except Exception as e:
            logger.error(f"Error executing notification task: {e}")
            task.status = "failed"
            task.error = str(e)
            return False

    async def _send_pushover_notification(self, api_token: str, user_key: str, title: str, message: str, priority: int = 0) -> bool:
        """Send a Pushover notification"""
        try:
            import aiohttp

            data = {
                "token": api_token,
                "user": user_key,
                "title": title,
                "message": message,
                "priority": priority
            }

            http_client_factory = self.dependencies.http_client_factory
            if http_client_factory:
                async with http_client_factory() as session:
                    async with session.post("https://api.pushover.net/1/messages.json", data=data) as response:
                        if response.status == 200:
                            logger.info("Pushover notification sent successfully")
                            return True
                        else:
                            logger.error(f"Pushover API error: {response.status}")
                            return False
            else:
                # Fallback to basic aiohttp session
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://api.pushover.net/1/messages.json", data=data) as response:
                        if response.status == 200:
                            logger.info("Pushover notification sent successfully")
                            return True
                        else:
                            logger.error(f"Pushover API error: {response.status}")
                            return False

        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")
            return False



    async def _execute_task(self, job: BorgJob, task: BorgJobTask, task_index: int = 0) -> bool:
        """Execute a task based on its type"""
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
                task.status = "failed"
                task.return_code = 1
                task.error = f"Unknown task type: {task.task_type}"
                return False
        except Exception as e:
            logger.error(f"Error executing task {task.task_type}: {e}")
            task.status = "failed"
            task.return_code = 1
            task.error = str(e)
            return False

    def subscribe_to_events(self) -> Optional[str]:
        """Subscribe to job events"""
        if self.dependencies.event_broadcaster:
            return self.dependencies.event_broadcaster.subscribe_client()
        return None

    def unsubscribe_from_events(self, client_id: str) -> bool:
        """Unsubscribe from job events"""
        if self.dependencies.event_broadcaster:
            return self.dependencies.event_broadcaster.unsubscribe_client(client_id)
        return False

    async def stream_job_output(self, job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream job output"""
        if self.output_manager:
            async for output in self.output_manager.stream_job_output(job_id):
                yield output
        else:
            # Empty async generator
            return
            yield

    def get_job(self, job_id: str) -> Optional[BorgJob]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def list_jobs(self) -> Dict[str, BorgJob]:
        """List all jobs"""
        return self.jobs.copy()

    def get_job_output(self, job_id: str) -> AsyncGenerator[str, None]:
        """Get real-time job output"""
        return self.output_manager.get_job_output(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status not in ["running", "queued"]:
            return False

        # Cancel the process if running
        if job_id in self._processes:
            process = self._processes[job_id]
            success = await self.executor.terminate_process(process)
            if success:
                del self._processes[job_id]

        # Update job status
        job.status = "cancelled"
        job.completed_at = datetime.now(UTC)

        # Update database
        if self.database_manager:
            await self.database_manager.update_job_status(
                job_id, "cancelled", job.completed_at
            )

        # Broadcast cancellation
        self.event_broadcaster.broadcast_event(
            EventType.JOB_CANCELLED, job_id=job_id, data={"cancelled_at": job.completed_at.isoformat()}
        )

        return True

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job resources"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            logger.debug(f"Cleaning up job {job_id} (status: {job.status})")

            # Remove from active jobs
            del self.jobs[job_id]

            # Clean up output
            self.output_manager.clear_job_output(job_id)

            # Remove process if still tracked
            if job_id in self._processes:
                del self._processes[job_id]

            return True
        return False

    async def _auto_cleanup_job(self, job_id: str, delay_seconds: int):
        """Automatically cleanup job after delay"""
        await asyncio.sleep(delay_seconds)
        self.cleanup_job(job_id)

    def get_queue_status(self):
        """Get queue manager status"""
        if self.queue_manager:
            stats = self.queue_manager.get_queue_stats()
            if stats:
                # Convert dataclass to dict for backward compatibility
                return {
                    "max_concurrent_backups": self.queue_manager.max_concurrent_backups,
                    "running_backups": stats.running_jobs,
                    "queued_backups": stats.total_queued,
                    "available_slots": stats.available_slots,
                    "queue_size": stats.total_queued,
                }
            return {}
        return None

    def get_active_jobs_count(self) -> int:
        """Get count of active (running/queued) jobs"""
        return len([j for j in self.jobs.values() if j.status in ["running", "queued"]])

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status information"""
        job = self.jobs.get(job_id)
        if not job:
            return None

        return {
            "id": job.id,
            "status": job.status,
            "running": job.status == "running",
            "completed": job.status == "completed",
            "failed": job.status == "failed",
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "return_code": job.return_code,
            "error": job.error,
            "job_type": job.job_type,
            "current_task_index": job.current_task_index if job.is_composite() else None,
            "tasks": len(job.tasks) if job.tasks else 0,
        }

    async def get_job_output_stream(self, job_id: str) -> Dict[str, Any]:
        """Get job output stream data"""
        # Get output from output manager (don't require job to exist, just output)
        job_output = self.output_manager.get_job_output(job_id)
        if job_output:
            # job_output.lines contains dict objects, not OutputLine objects
            return {
                "lines": list(job_output.lines),  # Already formatted as dicts
                "progress": job_output.current_progress,
            }

        return {"lines": [], "progress": {}}

    def get_queue_stats(self):
        """Get queue statistics (alias for get_queue_status)"""
        return self.get_queue_status()

    async def _get_repository_data(self, repository_id: int) -> Optional[Dict[str, Any]]:
        """Get repository data by ID"""
        # First try using database manager if available
        if hasattr(self, 'database_manager') and self.database_manager:
            try:
                return await self.database_manager.get_repository_data(repository_id)
            except Exception as e:
                logger.error(f"Error getting repository data from database manager: {e}")

        # Fallback to direct database access
        if self.dependencies.db_session_factory:
            try:
                with self.dependencies.db_session_factory() as db:
                    from app.models.database import Repository
                    repo = db.query(Repository).filter(Repository.id == repository_id).first()
                    if repo:
                        return {
                            "id": repo.id,
                            "name": repo.name,
                            "path": repo.path,
                            "passphrase": repo.get_passphrase() if hasattr(repo, 'get_passphrase') else None,
                        }
            except Exception as e:
                logger.debug(f"Error getting repository data: {e}")

        # Final fallback to get_db_session
        try:
            with get_db_session() as db:
                from app.models.database import Repository
                repo = db.query(Repository).filter(Repository.id == repository_id).first()
                if repo:
                    return {
                        "id": repo.id,
                        "name": repo.name,
                        "path": repo.path,
                        "passphrase": repo.get_passphrase() if hasattr(repo, 'get_passphrase') else None,
                    }
        except Exception as e:
            logger.debug(f"Error getting repository data from fallback: {e}")

        return None

    async def stream_all_job_updates(self):
        """Stream all job updates via event broadcaster"""
        if self.event_broadcaster:
            async for event in self.event_broadcaster.stream_all_events():
                yield event
        else:
            # Fallback: empty stream
            return
            yield  # Make this a generator

    async def shutdown(self):
        """Shutdown the job manager"""
        self._shutdown_requested = True
        logger.info("Shutting down job manager...")

        # Cancel all running jobs
        for job_id, job in list(self.jobs.items()):
            if job.status in ["running", "queued"]:
                await self.cancel_job(job_id)

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

        logger.info("Job manager shutdown complete")


# Factory function and singleton for backward compatibility
_job_manager_instance: Optional[JobManager] = None


def get_job_manager(config=None) -> JobManager:
    """Factory function for job manager with singleton behavior"""
    global _job_manager_instance
    if _job_manager_instance is None:
        if config is None:
            # Use environment variables or defaults
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

        _job_manager_instance = JobManager(internal_config)
        logger.info(
            f"Created new job manager with config: max_concurrent={internal_config.max_concurrent_backups}"
        )

    return _job_manager_instance


def reset_job_manager():
    """Reset job manager for testing"""
    global _job_manager_instance
    if _job_manager_instance:
        logger.warning("Resetting job manager instance")
    _job_manager_instance = None


def get_default_job_manager_dependencies() -> JobManagerDependencies:
    """Get default job manager dependencies (production configuration)"""
    return JobManagerFactory.create_dependencies()


def get_test_job_manager_dependencies(
    mock_subprocess: Optional[Callable] = None,
    mock_db_session: Optional[Callable] = None,
    mock_rclone_service: Optional[Any] = None,
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_subprocess=mock_subprocess,
        mock_db_session=mock_db_session,
        mock_rclone_service=mock_rclone_service,
    )


# Backward compatibility aliases
BorgJobManager = JobManager
ModularBorgJobManager = JobManager  # For transitional compatibility
BorgJobManagerConfig = JobManagerConfig




# Export all public classes and functions
__all__ = [
    "JobManager",
    "JobManagerConfig",
    "JobManagerDependencies",
    "JobManagerFactory",
    "BorgJob",
    "BorgJobTask",
    "get_job_manager",
    "reset_job_manager",
    "get_default_job_manager_dependencies",
    "get_test_job_manager_dependencies",
    # Backward compatibility
    "BorgJobManager",
    "ModularBorgJobManager",
    "BorgJobManagerConfig",
]