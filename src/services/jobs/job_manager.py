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

from services.jobs.job_executor import JobExecutor
from services.jobs.job_output_manager import JobOutputManager
from services.jobs.job_queue_manager import JobQueueManager, JobPriority
from services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
    EventType,
)
from services.jobs.job_database_manager import JobDatabaseManager, DatabaseJobData
from services.rclone_service import RcloneService
from utils.db_session import get_db_session

if TYPE_CHECKING:
    from models.database import Repository, Schedule
    from services.notifications.pushover_service import PushoverService

logger = logging.getLogger(__name__)


@dataclass
class JobManagerConfig:
    """Configuration for the job manager"""

    # Concurrency settings
    max_concurrent_backups: int = 5
    max_concurrent_operations: int = 10

    # Output and storage settings
    max_output_lines_per_job: int = 1000

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
    pushover_service: Optional["PushoverService"] = None

    # External dependencies (for testing/customization)
    subprocess_executor: Optional[Callable] = field(
        default_factory=lambda: asyncio.create_subprocess_exec
    )
    db_session_factory: Optional[Callable] = None
    rclone_service: Optional[Any] = None
    http_client_factory: Optional[Callable] = None
    encryption_service: Optional[Any] = None
    storage_factory: Optional[Any] = None
    provider_registry: Optional[Any] = None

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
            encryption_service=custom_dependencies.encryption_service,
            storage_factory=custom_dependencies.storage_factory,
            provider_registry=custom_dependencies.provider_registry,
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

        # PushoverService
        if custom_dependencies.pushover_service:
            deps.pushover_service = custom_dependencies.pushover_service
        else:
            from services.notifications.pushover_service import PushoverService

            deps.pushover_service = PushoverService()

        # Cloud Provider Services
        if not deps.encryption_service:
            from services.cloud_providers.service import EncryptionService

            deps.encryption_service = EncryptionService()

        if not deps.storage_factory:
            from services.cloud_providers.service import StorageFactory

            # Create storage factory with rclone service (create default if needed)
            rclone_service = deps.rclone_service
            if not rclone_service:
                from services.rclone_service import RcloneService

                rclone_service = RcloneService()
                deps.rclone_service = rclone_service
            deps.storage_factory = StorageFactory(rclone_service)

        # Provider Registry
        if not deps.provider_registry:
            from services.cloud_providers.registry_factory import RegistryFactory

            deps.provider_registry = RegistryFactory.get_default_registry()

        # Job Database Manager
        if custom_dependencies.database_manager:
            deps.database_manager = custom_dependencies.database_manager
        else:
            deps.database_manager = JobDatabaseManager(
                db_session_factory=deps.db_session_factory,
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
        self.pushover_service = dependencies.pushover_service

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
        """Start a Borg command (now always creates composite job with one task)"""
        await self.initialize()

        job_id = str(uuid.uuid4())

        # Create the main task for this command
        command_str = " ".join(command[:3]) + ("..." if len(command) > 3 else "")
        main_task = BorgJobTask(
            task_type="command",
            task_name=f"Execute: {command_str}",
            status="queued" if is_backup else "running",
            started_at=datetime.now(UTC),
        )

        # Create composite job (all jobs are now composite)
        job = BorgJob(
            id=job_id,
            command=command,
            job_type="composite",  # All jobs are now composite
            status="queued" if is_backup else "running",
            started_at=datetime.now(UTC),
            tasks=[main_task],  # Always has at least one task
        )
        self.jobs[job_id] = job

        self.output_manager.create_job_output(job_id)

        if is_backup:
            await self.queue_manager.enqueue_job(
                job_id=job_id, job_type="backup", priority=JobPriority.NORMAL
            )
        else:
            await self._execute_composite_task(job, main_task, command, env)

        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"command": command_str, "is_backup": is_backup},
        )

        return job_id

    async def _execute_composite_task(
        self,
        job: BorgJob,
        task: BorgJobTask,
        command: List[str],
        env: Optional[Dict] = None,
    ):
        """Execute a single task within a composite job"""
        job.status = "running"
        task.status = "running"

        try:
            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            def output_callback(line: str, progress: Dict):
                # Add output to both the task and the output manager
                task.output_lines.append(line)
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

            # Update task and job based on process result
            task.completed_at = datetime.now(UTC)
            task.return_code = result.return_code

            if result.return_code == 0:
                task.status = "completed"
                job.status = "completed"
            else:
                task.status = "failed"
                task.error = (
                    result.error
                    or f"Process failed with return code {result.return_code}"
                )
                job.status = "failed"
                job.error = task.error

            job.return_code = result.return_code
            job.completed_at = datetime.now(UTC)

            if result.error:
                task.error = result.error
                job.error = result.error

            self.event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(UTC)
            logger.error(f"Composite job task {job.id} execution failed: {e}")

            self.event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

        finally:
            if job.id in self._processes:
                del self._processes[job.id]

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
                            logger.info(
                                f"Saving task {task.task_type} to database - Status: {task.status}, Return Code: {task.return_code}, Output Lines: {len(task.output_lines)}"
                            )
                            await self.database_manager.save_job_tasks(
                                job.id, job.tasks
                            )
                            logger.info(
                                f"Successfully saved task {task.task_type} to database"
                            )
                        except Exception as e:
                            logger.error(f"Failed to update tasks in database: {e}")

                    # If task failed and it's critical, stop the job
                    if task.status == "failed" and task.task_type in ["backup"]:
                        logger.error(
                            f"Critical task {task.task_type} failed, stopping job"
                        )
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
                            logger.info(
                                f"Saving exception task {task.task_type} to database - Status: {task.status}, Return Code: {task.return_code}, Output Lines: {len(task.output_lines)}"
                            )
                            await self.database_manager.save_job_tasks(
                                job.id, job.tasks
                            )
                            logger.info(
                                f"Successfully saved exception task {task.task_type} to database"
                            )
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
                data={
                    "status": job.status,
                    "completed_at": job.completed_at.isoformat(),
                },
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

    async def _execute_simple_job(
        self, job: BorgJob, command: List[str], env: Optional[Dict] = None
    ):
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

    async def _execute_backup_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a backup task using JobExecutor"""
        try:
            from utils.security import build_secure_borg_command

            params = task.parameters

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
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": line,
                        "progress": progress,
                        "task_index": job.current_task_index,
                    },
                )

            # Build backup command
            source_path = params.get("source_path")
            excludes = params.get("excludes", [])
            archive_name = params.get(
                "archive_name", f"backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
            )

            logger.info(
                f"Backup task parameters - source_path: {source_path}, excludes: {excludes}, archive_name: {archive_name}"
            )
            logger.info(f"All task parameters: {params}")

            additional_args = []
            additional_args.extend(["--stats", "--list"])
            additional_args.extend(["--filter", "AME"])

            for exclude in excludes:
                additional_args.extend(["--exclude", exclude])

            additional_args.append(f"{repository_path}::{archive_name}")

            additional_args.append(source_path)

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
            logger.info(
                f"Backup process completed with return code: {result.return_code}"
            )
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
                    for line in full_output.split("\n"):
                        if line.strip():
                            task.output_lines.append(line)
                            # Also add to output manager for real-time display
                            asyncio.create_task(
                                self.output_manager.add_output_line(
                                    job.id, line, "stdout", {}
                                )
                            )

            if result.error:
                task.error = result.error
            elif result.return_code != 0:
                # Set a default error message if none provided by result
                # Since stderr is redirected to stdout, check stdout for error messages
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

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in backup task execution: {str(e)}")
            task.status = "failed"
            task.return_code = 1
            task.error = f"Backup task failed: {str(e)}"
            task.completed_at = datetime.now(UTC)
            return False

    async def _execute_prune_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a prune task using JobExecutor"""
        try:
            params = task.parameters

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
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            result = await self.executor.execute_prune_task(
                repository_path=repository_path,
                passphrase=passphrase,
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

        except Exception as e:
            logger.error(f"Exception in prune task: {str(e)}")
            task.status = "failed"
            task.return_code = -1
            task.error = f"Prune task failed: {str(e)}"
            task.completed_at = datetime.now(UTC)
            return False

    async def _execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a repository check task"""
        try:
            from utils.security import build_secure_borg_command

            params = task.parameters

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
                    self.output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            additional_args = []

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

            process = await self.executor.start_process(command, env)
            self._processes[job.id] = process

            result = await self.executor.monitor_process_output(
                process, output_callback=task_output_callback
            )

            if job.id in self._processes:
                del self._processes[job.id]

            task.return_code = result.return_code
            task.status = "completed" if result.return_code == 0 else "failed"
            task.completed_at = datetime.now(UTC)

            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output:
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
                    error_lines = output_text.split("\n")[-5:] if output_text else []
                    stderr_text = (
                        "\n".join(error_lines) if error_lines else "No output captured"
                    )
                else:
                    stderr_text = "No output captured"
                task.error = (
                    f"Check failed with return code {result.return_code}: {stderr_text}"
                )

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Error executing check task for job {job.id}: {str(e)}")
            task.status = "failed"
            task.return_code = 1
            task.error = str(e)
            task.completed_at = datetime.now(UTC)
            return False

    async def _execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a cloud sync task using JobExecutor"""
        params = task.parameters

        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository not found"
            task.completed_at = datetime.now(UTC)
            return False

        repository_path = repo_data.get("path") or params.get("repository_path")
        passphrase = repo_data.get("passphrase") or params.get("passphrase")
        
        # Validate required parameters
        if not repository_path:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository path is required for cloud sync"
            task.completed_at = datetime.now(UTC)
            return False
            
        if not passphrase:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository passphrase is required for cloud sync"
            task.completed_at = datetime.now(UTC)
            return False

        def task_output_callback(line: str, progress: Dict):
            task.output_lines.append(line)
            asyncio.create_task(
                self.output_manager.add_output_line(job.id, line, "stdout", progress)
            )

        # Get cloud sync config ID, defaulting to None if not configured
        cloud_sync_config_id = params.get("cloud_sync_config_id")
        
        # Handle skip case at caller level instead of inside executor
        if not cloud_sync_config_id:
            logger.info("No cloud backup configuration - skipping cloud sync")
            task.status = "completed"
            task.return_code = 0
            task.completed_at = datetime.now(UTC)
            # Add output line for UI feedback
            task.output_lines.append("Cloud sync skipped - no configuration")
            asyncio.create_task(
                self.output_manager.add_output_line(
                    job.id, "Cloud sync skipped - no configuration", "stdout", {}
                )
            )
            return True
        
        result = await self.executor.execute_cloud_sync_task(
            repository_path=repository_path,
            cloud_sync_config_id=cloud_sync_config_id,
            db_session_factory=self.dependencies.db_session_factory,
            rclone_service=self.dependencies.rclone_service,
            encryption_service=self.dependencies.encryption_service,
            storage_factory=self.dependencies.storage_factory,
            provider_registry=self.dependencies.provider_registry,
            output_callback=task_output_callback,
        )

        task.return_code = result.return_code
        task.status = "completed" if result.return_code == 0 else "failed"
        if result.error:
            task.error = result.error

        return result.return_code == 0

    async def _execute_notification_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a notification task"""
        params = task.parameters

        notification_config_id = params.get("notification_config_id") or params.get(
            "config_id"
        )
        if not notification_config_id:
            logger.info(
                "No notification configuration provided - skipping notification"
            )
            task.status = "failed"
            task.return_code = 1
            task.error = "No notification configuration"
            return False

        try:
            with get_db_session() as db:
                from models.database import NotificationConfig

                config = (
                    db.query(NotificationConfig)
                    .filter(NotificationConfig.id == notification_config_id)
                    .first()
                )

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
                    user_key, app_token = config.get_pushover_credentials()

                    title = params.get("title", "Borgitory Notification")
                    message = params.get("message", "Job completed")
                    priority = params.get("priority", 0)

                    task.output_lines.append(
                        {"text": f"Sending Pushover notification to {config.name}"}
                    )
                    task.output_lines.append({"text": f"Title: {title}"})
                    task.output_lines.append({"text": f"Message: {message}"})
                    task.output_lines.append({"text": f"Priority: {priority}"})

                    self.event_broadcaster.broadcast_event(
                        EventType.JOB_OUTPUT,
                        job_id=job.id,
                        data={
                            "line": f"Sending Pushover notification to {config.name}",
                            "task_index": task_index,
                        },
                    )

                    if self.pushover_service:
                        (
                            success,
                            response_message,
                        ) = await self.pushover_service.send_notification_with_response(
                            user_key=user_key,
                            app_token=app_token,
                            title=title,
                            message=message,
                            priority=priority,
                        )
                    else:
                        success = False
                        response_message = "PushoverService not available"

                    if success:
                        result_message = "✓ Notification sent successfully"
                        task.output_lines.append({"text": result_message})
                        if response_message:
                            task.output_lines.append(
                                {"text": f"Response: {response_message}"}
                            )
                    else:
                        result_message = (
                            f"✗ Failed to send notification: {response_message}"
                        )
                        task.output_lines.append({"text": result_message})

                    self.event_broadcaster.broadcast_event(
                        EventType.JOB_OUTPUT,
                        job_id=job.id,
                        data={"line": result_message, "task_index": task_index},
                    )

                    task.status = "completed" if success else "failed"
                    task.return_code = 0 if success else 1
                    if not success:
                        task.error = (
                            response_message or "Failed to send Pushover notification"
                        )
                    return success
                else:
                    logger.warning(
                        f"Unsupported notification provider: {config.provider}"
                    )
                    task.status = "failed"
                    task.error = f"Unsupported provider: {config.provider}"
                    return False

        except Exception as e:
            logger.error(f"Error executing notification task: {e}")
            task.status = "failed"
            task.error = str(e)
            return False

    async def _execute_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
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

    async def stream_job_output(
        self, job_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream job output"""
        if self.output_manager:
            async for output in self.output_manager.stream_job_output(job_id):
                yield output
        else:
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

        if job_id in self._processes:
            process = self._processes[job_id]
            success = await self.executor.terminate_process(process)
            if success:
                del self._processes[job_id]

        job.status = "cancelled"
        job.completed_at = datetime.now(UTC)

        if self.database_manager:
            await self.database_manager.update_job_status(
                job_id, "cancelled", job.completed_at
            )

        self.event_broadcaster.broadcast_event(
            EventType.JOB_CANCELLED,
            job_id=job_id,
            data={"cancelled_at": job.completed_at.isoformat()},
        )

        return True

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job resources"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            logger.debug(f"Cleaning up job {job_id} (status: {job.status})")

            del self.jobs[job_id]

            self.output_manager.clear_job_output(job_id)

            if job_id in self._processes:
                del self._processes[job_id]

            return True
        return False

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
            "current_task_index": job.current_task_index if job.tasks else None,
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

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data by ID"""
        # First try using database manager if available
        if hasattr(self, "database_manager") and self.database_manager:
            try:
                return await self.database_manager.get_repository_data(repository_id)
            except Exception as e:
                logger.error(
                    f"Error getting repository data from database manager: {e}"
                )

        # Fallback to direct database access
        if self.dependencies.db_session_factory:
            try:
                with self.dependencies.db_session_factory() as db:
                    from models.database import Repository

                    repo = (
                        db.query(Repository)
                        .filter(Repository.id == repository_id)
                        .first()
                    )
                    if repo:
                        return {
                            "id": repo.id,
                            "name": repo.name,
                            "path": repo.path,
                            "passphrase": repo.get_passphrase()
                            if hasattr(repo, "get_passphrase")
                            else None,
                        }
            except Exception as e:
                logger.debug(f"Error getting repository data: {e}")

        # Final fallback to get_db_session
        try:
            with get_db_session() as db:
                from models.database import Repository

                repo = (
                    db.query(Repository).filter(Repository.id == repository_id).first()
                )
                if repo:
                    return {
                        "id": repo.id,
                        "name": repo.name,
                        "path": repo.path,
                        "passphrase": repo.get_passphrase()
                        if hasattr(repo, "get_passphrase")
                        else None,
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

        # Clear data
        self.jobs.clear()
        self._processes.clear()

        logger.info("Job manager shutdown complete")

    # Bridge methods for external job registration (BackupService integration)

    def register_external_job(
        self, job_id: str, job_type: str = "backup", job_name: str = "External Backup"
    ) -> None:
        """
        Register an external job (from BackupService) for monitoring purposes.
        All jobs are now composite jobs with at least one task.

        Args:
            job_id: Unique job identifier
            job_type: Type of job (backup, prune, check, etc.)
            job_name: Human-readable job name
        """
        if job_id in self.jobs:
            logger.warning(f"Job {job_id} already registered, updating status")

        # Create the main task for this job
        main_task = BorgJobTask(
            task_type=job_type,
            task_name=job_name,
            status="running",
            started_at=datetime.now(UTC),
        )

        # Create a composite BorgJob (all jobs are now composite)
        job = BorgJob(
            id=job_id,
            command=[],  # External jobs don't have direct commands
            job_type="composite",  # All jobs are now composite
            status="running",
            started_at=datetime.now(UTC),
            repository_id=None,  # Can be set later if needed
            schedule=None,
            tasks=[main_task],  # Always has at least one task
        )

        self.jobs[job_id] = job

        # Initialize output tracking
        self.output_manager.create_job_output(job_id)

        # Broadcast job started event
        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"job_type": job_type, "job_name": job_name, "external": True},
        )

        logger.info(
            f"Registered external composite job {job_id} ({job_type}) with 1 task for monitoring"
        )

    def update_external_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        return_code: Optional[int] = None,
    ) -> None:
        """
        Update the status of an external job and its main task.

        Args:
            job_id: Job identifier
            status: New status (running, completed, failed, etc.)
            error: Error message if failed
            return_code: Process return code
        """
        if job_id not in self.jobs:
            logger.warning(f"Cannot update external job {job_id} - not registered")
            return

        job = self.jobs[job_id]
        old_status = job.status
        job.status = status

        if error:
            job.error = error

        if return_code is not None:
            job.return_code = return_code

        if status in ["completed", "failed"]:
            job.completed_at = datetime.now(UTC)

        # Update the main task status as well
        if job.tasks:
            main_task = job.tasks[0]  # First task is the main task
            main_task.status = status
            if error:
                main_task.error = error
            if return_code is not None:
                main_task.return_code = return_code
            if status in ["completed", "failed"]:
                main_task.completed_at = datetime.now(UTC)

        # Broadcast status change event
        if old_status != status:
            if status == "completed":
                event_type = EventType.JOB_COMPLETED
            elif status == "failed":
                event_type = EventType.JOB_FAILED
            else:
                event_type = EventType.JOB_UPDATED

            self.event_broadcaster.broadcast_event(
                event_type,
                job_id=job_id,
                data={"old_status": old_status, "new_status": status, "external": True},
            )

        logger.debug(
            f"Updated external job {job_id} and main task status: {old_status} -> {status}"
        )

    def add_external_job_output(self, job_id: str, output_line: str) -> None:
        """
        Add output line to an external job's main task.

        Args:
            job_id: Job identifier
            output_line: Output line to add
        """
        if job_id not in self.jobs:
            logger.warning(
                f"Cannot add output to external job {job_id} - not registered"
            )
            return

        job = self.jobs[job_id]

        # Add output to the main task
        if job.tasks:
            main_task = job.tasks[0]
            # Store output in dictionary format for consistency with task streaming
            main_task.output_lines.append({"text": output_line})

        # Also add output through output manager for streaming
        asyncio.create_task(self.output_manager.add_output_line(job_id, output_line))

        # Broadcast output event for real-time streaming
        self.event_broadcaster.broadcast_event(
            EventType.JOB_OUTPUT,
            job_id=job_id,
            data={
                "line": output_line,
                "task_index": 0,  # External jobs use main task (index 0)
                "progress": None,
            },
        )

    def unregister_external_job(self, job_id: str) -> None:
        """
        Unregister an external job (cleanup after completion).

        Args:
            job_id: Job identifier to unregister
        """
        if job_id in self.jobs:
            job = self.jobs[job_id]
            logger.info(
                f"Unregistering external job {job_id} (final status: {job.status})"
            )

            # Use existing cleanup method
            self.cleanup_job(job_id)
        else:
            logger.warning(f"Cannot unregister external job {job_id} - not found")


# Factory function for creating JobManager instances (no singleton)
def create_job_manager(config=None, rclone_service: RcloneService = None) -> JobManager:
    """Factory function for creating JobManager instances"""
    if config is None:
        # Use environment variables or defaults
        internal_config = JobManagerConfig(
            max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
            max_output_lines_per_job=int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000")),
        )
    elif hasattr(config, "to_internal_config"):
        # Backward compatible config wrapper
        internal_config = config.to_internal_config()
    else:
        # Assume it's already a JobManagerConfig
        internal_config = config

    # Create dependencies with rclone service
    custom_deps = JobManagerDependencies(rclone_service=rclone_service)

    dependencies = JobManagerFactory.create_dependencies(
        config=internal_config, custom_dependencies=custom_deps
    )

    job_manager = JobManager(config=internal_config, dependencies=dependencies)
    logger.info(
        f"Created new job manager with config: max_concurrent={internal_config.max_concurrent_backups}"
    )

    return job_manager


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
    "create_job_manager",
    "get_default_job_manager_dependencies",
    "get_test_job_manager_dependencies",
    # Backward compatibility
    "BorgJobManager",
    "ModularBorgJobManager",
    "BorgJobManagerConfig",
]
