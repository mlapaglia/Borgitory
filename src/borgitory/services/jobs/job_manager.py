"""
Job Manager - Consolidated modular job management system

This file consolidates the job management functionality from multiple files into a single,
clean architecture following the same pattern as other services in the application.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from typing import (
    Union,
    Dict,
    Optional,
    List,
    AsyncGenerator,
    Callable,
    Coroutine,
    TYPE_CHECKING,
    Any,
)

from borgitory.protocols.job_protocols import TaskDefinition
from dataclasses import dataclass, field

from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.jobs.job_output_manager import JobOutputManager
from borgitory.services.jobs.job_queue_manager import (
    QueuedJob,
    JobQueueManager,
    JobPriority,
)
from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
)
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.jobs.broadcaster.job_event import JobEvent
from borgitory.services.jobs.job_database_manager import (
    JobDatabaseManager,
    DatabaseJobData,
)
from borgitory.services.rclone_service import RcloneService
from borgitory.utils.db_session import get_db_session
from contextlib import _GeneratorContextManager

from borgitory.utils.security import (
    secure_borg_command,
    cleanup_temp_keyfile,
)

if TYPE_CHECKING:
    from asyncio.subprocess import Process
    from borgitory.models.database import Repository, Schedule
    from borgitory.protocols.command_protocols import ProcessExecutorProtocol
    from borgitory.dependencies import ApplicationScopedNotificationService
    from sqlalchemy.orm import Session
    from borgitory.services.notifications.providers.discord_provider import HttpClient
    from borgitory.services.cloud_providers import StorageFactory
    from borgitory.services.encryption_service import EncryptionService
    from borgitory.services.cloud_providers.registry import ProviderRegistry
    from borgitory.services.hooks.hook_execution_service import HookExecutionService

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
    job_executor: Optional["ProcessExecutorProtocol"] = None
    output_manager: Optional[JobOutputManager] = None
    queue_manager: Optional[JobQueueManager] = None
    event_broadcaster: Optional[JobEventBroadcaster] = None
    database_manager: Optional[JobDatabaseManager] = None

    # External dependencies (for testing/customization)
    subprocess_executor: Optional[Callable[..., Coroutine[None, None, "Process"]]] = (
        field(default_factory=lambda: asyncio.create_subprocess_exec)
    )
    db_session_factory: Optional[Callable[[], _GeneratorContextManager["Session"]]] = (
        None
    )
    rclone_service: Optional[RcloneService] = None
    http_client_factory: Optional[Callable[[], "HttpClient"]] = None
    encryption_service: Optional["EncryptionService"] = None
    storage_factory: Optional["StorageFactory"] = None
    provider_registry: Optional["ProviderRegistry"] = None
    # Use semantic type alias for application-scoped notification service
    notification_service: Optional["ApplicationScopedNotificationService"] = None
    hook_execution_service: Optional["HookExecutionService"] = None

    def __post_init__(self) -> None:
        """Initialize default dependencies if not provided"""
        if self.db_session_factory is None:
            self.db_session_factory = self._default_db_session_factory

    def _default_db_session_factory(self) -> _GeneratorContextManager["Session"]:
        """Default database session factory"""
        return get_db_session()


@dataclass
class BorgJobTask:
    """Individual task within a job"""

    task_type: str  # 'backup', 'prune', 'check', 'cloud_sync', 'hook', 'notification'
    task_name: str
    status: str = "pending"  # 'pending', 'running', 'completed', 'failed', 'skipped'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    parameters: Dict[str, object] = field(default_factory=dict)
    output_lines: List[Union[str, Dict[str, str]]] = field(
        default_factory=list
    )  # Store task output


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
            notification_service=custom_dependencies.notification_service,
            hook_execution_service=custom_dependencies.hook_execution_service,
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

        if custom_dependencies.database_manager:
            deps.database_manager = custom_dependencies.database_manager
        else:
            deps.database_manager = JobDatabaseManager(
                db_session_factory=deps.db_session_factory,
            )

        return deps

    @classmethod
    def create_complete_dependencies(
        cls,
        config: Optional[JobManagerConfig] = None,
    ) -> JobManagerDependencies:
        """Create a complete set of dependencies with all cloud sync services for production use"""

        if config is None:
            config = JobManagerConfig()

        # Import dependencies from the DI system
        from borgitory.dependencies import (
            get_rclone_service,
            get_encryption_service,
            get_storage_factory,
            get_registry_factory,
            get_provider_registry,
            get_hook_execution_service,
        )

        # Create complete dependencies with all cloud sync and notification services
        # Import singleton dependency functions
        from borgitory.dependencies import get_notification_service_singleton

        complete_deps = JobManagerDependencies(
            rclone_service=get_rclone_service(),
            encryption_service=get_encryption_service(),
            storage_factory=get_storage_factory(get_rclone_service()),
            provider_registry=get_provider_registry(
                registry_factory=get_registry_factory()
            ),
            notification_service=get_notification_service_singleton(),
            hook_execution_service=get_hook_execution_service(),
        )

        return cls.create_dependencies(config=config, custom_dependencies=complete_deps)

    @classmethod
    def create_for_testing(
        cls,
        mock_subprocess: Optional[Callable[..., Any]] = None,
        mock_db_session: Optional[Callable[[], Any]] = None,
        mock_rclone_service: Optional[Any] = None,
        mock_http_client: Optional[Callable[[], Any]] = None,
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

        return cls.create_complete_dependencies(config=config)


class JobManager:
    """
    Main Job Manager using dependency injection and modular architecture
    """

    def __init__(
        self,
        config: Optional[JobManagerConfig] = None,
        dependencies: Optional[JobManagerDependencies] = None,
    ) -> None:
        self.config = config or JobManagerConfig()

        if dependencies is None:
            dependencies = JobManagerFactory.create_complete_dependencies()

        self.dependencies = dependencies

        self.executor = dependencies.job_executor
        self.output_manager = dependencies.output_manager
        self.queue_manager = dependencies.queue_manager
        self.event_broadcaster = dependencies.event_broadcaster
        self.database_manager = dependencies.database_manager
        # Use semantic type alias for application-scoped notification service
        from borgitory.dependencies import ApplicationScopedNotificationService

        self.notification_service: Optional[ApplicationScopedNotificationService] = (
            dependencies.notification_service
        )

        self.jobs: Dict[str, BorgJob] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}

        self._initialized = False
        self._shutdown_requested = False

        self._setup_callbacks()

    @property
    def safe_executor(self) -> "ProcessExecutorProtocol":
        if self.executor is None:
            raise RuntimeError(
                "JobManager executor is None - ensure proper initialization"
            )
        return self.executor

    @property
    def safe_output_manager(self) -> JobOutputManager:
        if self.output_manager is None:
            raise RuntimeError(
                "JobManager output_manager is None - ensure proper initialization"
            )
        return self.output_manager

    @property
    def safe_queue_manager(self) -> JobQueueManager:
        if self.queue_manager is None:
            raise RuntimeError(
                "JobManager queue_manager is None - ensure proper initialization"
            )
        return self.queue_manager

    @property
    def safe_event_broadcaster(self) -> JobEventBroadcaster:
        if self.event_broadcaster is None:
            raise RuntimeError(
                "JobManager event_broadcaster is None - ensure proper initialization"
            )
        return self.event_broadcaster

    def _setup_callbacks(self) -> None:
        """Set up callbacks between modules"""
        if self.queue_manager:
            self.queue_manager.set_callbacks(
                job_start_callback=self._on_job_start,
                job_complete_callback=self._on_job_complete,
            )

    async def initialize(self) -> None:
        """Initialize all modules"""
        if self._initialized:
            return

        if self.queue_manager:
            await self.queue_manager.initialize()

        if self.event_broadcaster:
            await self.safe_event_broadcaster.initialize()

        self._initialized = True
        logger.info("Job manager initialized successfully")

    async def start_borg_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        is_backup: bool = False,
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
            started_at=now_utc(),
        )

        # Create composite job (all jobs are now composite)
        job = BorgJob(
            id=job_id,
            command=command,
            job_type="composite",  # All jobs are now composite
            status="queued" if is_backup else "running",
            started_at=now_utc(),
            tasks=[main_task],  # Always has at least one task
        )
        self.jobs[job_id] = job

        self.safe_output_manager.create_job_output(job_id)

        if is_backup:
            await self.safe_queue_manager.enqueue_job(
                job_id=job_id, job_type="backup", priority=JobPriority.NORMAL
            )
        else:
            await self._execute_composite_task(job, main_task, command, env)

        self.safe_event_broadcaster.broadcast_event(
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
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        """Execute a single task within a composite job"""
        job.status = "running"
        task.status = "running"

        try:
            process = await self.safe_executor.start_process(command, env)
            self._processes[job.id] = process

            def output_callback(line: str) -> None:
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                # Add output to both the task and the output manager
                task.output_lines.append(line)
                asyncio.create_task(
                    self.safe_output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.safe_event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": None},  # No progress data
                )

            result = await self.safe_executor.monitor_process_output(
                process, output_callback=output_callback
            )

            # Update task and job based on process result
            task.completed_at = now_utc()
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
            job.completed_at = now_utc()

            if result.error:
                task.error = result.error
                job.error = result.error

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = now_utc()
            job.status = "failed"
            job.error = str(e)
            job.completed_at = now_utc()
            logger.error(f"Composite job task {job.id} execution failed: {e}")

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

        finally:
            if job.id in self._processes:
                del self._processes[job.id]

    def _on_job_start(self, job_id: str, queued_job: QueuedJob) -> None:
        """Callback when queue manager starts a job"""
        job = self.jobs.get(job_id)
        if job and job.command:
            asyncio.create_task(self._execute_simple_job(job, job.command))

    def _on_job_complete(self, job_id: str, success: bool) -> None:
        """Callback when queue manager completes a job"""
        job = self.jobs.get(job_id)
        if job:
            logger.info(f"Job {job_id} completed with success={success}")

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List["TaskDefinition"],
        repository: "Repository",
        schedule: Optional["Schedule"] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a composite job with multiple tasks"""
        await self.initialize()

        job_id = str(uuid.uuid4())

        tasks = []
        for task_def in task_definitions:
            # Create parameters dict from the TaskDefinition
            parameters: Dict[str, object] = {
                "type": task_def.type,
                "name": task_def.name,
                **task_def.parameters,
            }
            if task_def.priority is not None:
                parameters["priority"] = task_def.priority
            if task_def.timeout is not None:
                parameters["timeout"] = task_def.timeout
            if task_def.retry_count is not None:
                parameters["retry_count"] = task_def.retry_count

            task = BorgJobTask(
                task_type=task_def.type,
                task_name=task_def.name,
                parameters=parameters,
            )
            tasks.append(task)

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="pending",
            started_at=now_utc(),
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

        self.safe_output_manager.create_job_output(job_id)

        asyncio.create_task(self._execute_composite_job(job))

        self.safe_event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"job_type": job_type, "task_count": len(tasks)},
        )

        return job_id

    async def _execute_composite_job(self, job: BorgJob) -> None:
        """Execute a composite job with multiple sequential tasks"""
        job.status = "running"

        # Update job status in database
        if self.database_manager:
            await self.database_manager.update_job_status(job.id, "running")

        self.safe_event_broadcaster.broadcast_event(
            EventType.JOB_STATUS_CHANGED,
            job_id=job.id,
            data={"status": "running", "started_at": job.started_at.isoformat()},
        )

        try:
            for task_index, task in enumerate(job.tasks):
                job.current_task_index = task_index

                task.status = "running"
                task.started_at = now_utc()

                self.safe_event_broadcaster.broadcast_event(
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
                    elif task.task_type == "hook":
                        # For post-hooks, determine if job has failed so far
                        hook_type = task.parameters.get("hook_type", "unknown")
                        job_has_failed = False
                        if hook_type == "post":
                            # Check if any previous tasks have failed
                            previous_tasks = job.tasks[:task_index]
                            job_has_failed = any(
                                t.status == "failed"
                                and (
                                    t.task_type in ["backup"]  # Critical task types
                                    or (
                                        t.task_type == "hook"
                                        and t.parameters.get("critical_failure", False)
                                    )  # Critical hooks
                                )
                                for t in previous_tasks
                            )
                        await self._execute_hook_task(
                            job, task, task_index, job_has_failed
                        )
                    else:
                        await self._execute_task(job, task, task_index)

                    # Task status, return_code, and completed_at are already set by the individual task methods
                    # Just ensure completed_at is set if not already
                    if not task.completed_at:
                        task.completed_at = now_utc()

                    self.safe_event_broadcaster.broadcast_event(
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

                    if task.status == "failed":
                        is_critical_hook_failure = (
                            task.task_type == "hook"
                            and task.parameters.get("critical_failure", False)
                        )
                        is_critical_task = task.task_type in ["backup"]

                        if is_critical_hook_failure or is_critical_task:
                            failed_hook_name = task.parameters.get(
                                "failed_critical_hook_name", "unknown"
                            )
                            logger.error(
                                f"Critical {'hook' if is_critical_hook_failure else 'task'} "
                                f"{'(' + str(failed_hook_name) + ') ' if is_critical_hook_failure else ''}"
                                f"{task.task_type} failed, stopping job"
                            )

                            remaining_tasks = job.tasks[task_index + 1 :]
                            for remaining_task in remaining_tasks:
                                if remaining_task.status == "pending":
                                    remaining_task.status = "skipped"
                                    remaining_task.completed_at = now_utc()
                                    remaining_task.output_lines.append(
                                        f"Task skipped due to critical {'hook' if is_critical_hook_failure else 'task'} failure"
                                    )
                                    logger.info(
                                        f"Marked task {remaining_task.task_type} as skipped due to critical failure"
                                    )

                            # Save all tasks to database after marking remaining as skipped
                            if self.database_manager:
                                try:
                                    logger.info(
                                        f"Saving all tasks to database after critical failure - Job: {job.id}"
                                    )
                                    await self.database_manager.save_job_tasks(
                                        job.id, job.tasks
                                    )
                                    logger.info(
                                        "Successfully saved all tasks to database after critical failure"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to update tasks in database after critical failure: {e}"
                                    )

                            break

                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                    task.completed_at = now_utc()
                    logger.error(f"Task {task.task_type} in job {job.id} failed: {e}")

                    self.safe_event_broadcaster.broadcast_event(
                        EventType.TASK_FAILED,
                        job_id=job.id,
                        data={"task_index": task_index, "error": str(e)},
                    )

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

                    if task.task_type in ["backup"]:
                        remaining_tasks = job.tasks[task_index + 1 :]
                        for remaining_task in remaining_tasks:
                            if remaining_task.status == "pending":
                                remaining_task.status = "skipped"
                                remaining_task.completed_at = now_utc()
                                remaining_task.output_lines.append(
                                    "Task skipped due to critical task exception"
                                )
                                logger.info(
                                    f"Marked task {remaining_task.task_type} as skipped due to critical task exception"
                                )

                        # Save all tasks to database after marking remaining as skipped
                        if self.database_manager:
                            try:
                                logger.info(
                                    f"Saving all tasks to database after critical exception - Job: {job.id}"
                                )
                                await self.database_manager.save_job_tasks(
                                    job.id, job.tasks
                                )
                                logger.info(
                                    "Successfully saved all tasks to database after critical exception"
                                )
                            except Exception as db_e:
                                logger.error(
                                    f"Failed to update tasks in database after critical exception: {db_e}"
                                )

                        break

            failed_tasks = [t for t in job.tasks if t.status == "failed"]
            completed_tasks = [t for t in job.tasks if t.status == "completed"]
            skipped_tasks = [t for t in job.tasks if t.status == "skipped"]
            finished_tasks = completed_tasks + skipped_tasks

            if len(finished_tasks) + len(failed_tasks) == len(job.tasks):
                if failed_tasks:
                    critical_task_failed = any(
                        t.task_type in ["backup"] for t in failed_tasks
                    )
                    critical_hook_failed = any(
                        t.task_type == "hook"
                        and t.parameters.get("critical_failure", False)
                        for t in failed_tasks
                    )
                    job.status = (
                        "failed"
                        if (critical_task_failed or critical_hook_failed)
                        else "completed"
                    )
                else:
                    job.status = "completed"
            else:
                job.status = "failed"

            job.completed_at = now_utc()

            # Update final job status
            if self.database_manager:
                await self.database_manager.update_job_status(
                    job.id, job.status, job.completed_at
                )

            self.safe_event_broadcaster.broadcast_event(
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
            job.completed_at = now_utc()
            logger.error(f"Composite job {job.id} execution failed: {e}")

            if self.database_manager:
                await self.database_manager.update_job_status(
                    job.id, "failed", job.completed_at, None, None, str(e)
                )

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

    async def _execute_simple_job(
        self, job: BorgJob, command: List[str], env: Optional[Dict[str, str]] = None
    ) -> None:
        """Execute a simple single-command job (for test compatibility)"""
        job.status = "running"

        try:
            process = await self.safe_executor.start_process(command, env)
            self._processes[job.id] = process

            def output_callback(line: str) -> None:
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.safe_output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.safe_event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": line, "progress": None},  # No progress data
                )

            result = await self.safe_executor.monitor_process_output(
                process, output_callback=output_callback
            )

            job.status = "completed" if result.return_code == 0 else "failed"
            job.return_code = result.return_code
            job.completed_at = now_utc()

            if result.error:
                job.error = result.error

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == "completed"
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = now_utc()
            logger.error(f"Job {job.id} execution failed: {e}")

            self.safe_event_broadcaster.broadcast_event(
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
            params = task.parameters

            if job.repository_id is None:
                task.status = "failed"
                task.error = "Repository ID is missing"
                return False
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                task.status = "failed"
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = now_utc()
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = str(
                repo_data.get("passphrase") or params.get("passphrase") or ""
            )
            keyfile_content = repo_data.get("keyfile_content")
            if keyfile_content is not None and not isinstance(keyfile_content, str):
                keyfile_content = None  # Ensure it's str or None

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.safe_output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

                self.safe_event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": line,
                        "progress": None,  # No progress data
                        "task_index": job.current_task_index,
                    },
                )

            # Build backup command
            source_path = params.get("source_path")
            excludes = params.get("excludes", [])
            if not isinstance(excludes, list):
                excludes = []
            archive_name = params.get(
                "archive_name", f"backup-{now_utc().strftime('%Y%m%d-%H%M%S')}"
            )

            logger.info(
                f"Backup task parameters - source_path: {source_path}, excludes: {excludes}, archive_name: {archive_name}"
            )
            logger.info(f"All task parameters: {params}")

            additional_args = []
            additional_args.extend(["--stats", "--list"])
            additional_args.extend(["--filter", "AME"])

            dry_run = params.get("dry_run", False)
            if dry_run:
                additional_args.append("--dry-run")

            for exclude in excludes:
                additional_args.extend(["--exclude", exclude])

            additional_args.append(f"{repository_path}::{archive_name}")

            if source_path:
                additional_args.append(str(source_path))

            logger.info(f"Final additional_args for Borg command: {additional_args}")

            ignore_lock = params.get("ignore_lock", False)
            if ignore_lock:
                logger.info(f"Running borg break-lock on repository: {repository_path}")
                try:
                    await self._execute_break_lock(
                        str(repository_path),
                        passphrase,
                        task_output_callback,
                        keyfile_content,
                    )
                except Exception as e:
                    logger.warning(f"Break-lock failed, continuing with backup: {e}")
                    task_output_callback(f"Warning: Break-lock failed: {e}")

            async with secure_borg_command(
                base_command="borg create",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=additional_args,
                cleanup_keyfile=False,
            ) as (command, env, temp_keyfile_path):
                process = await self.safe_executor.start_process(command, env)
                self._processes[job.id] = process

                if temp_keyfile_path:
                    setattr(task, "_temp_keyfile_path", temp_keyfile_path)

            # Monitor the process (outside context manager since it's long-running)
            result = await self.safe_executor.monitor_process_output(
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

            if job.id in self._processes:
                del self._processes[job.id]

            task.return_code = result.return_code
            task.status = "completed" if result.return_code == 0 else "failed"
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
                                self.safe_output_manager.add_output_line(
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

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in backup task execution: {str(e)}")
            task.status = "failed"
            task.return_code = 1
            task.error = f"Backup task failed: {str(e)}"
            task.completed_at = now_utc()

            if hasattr(task, "_temp_keyfile_path"):
                cleanup_temp_keyfile(getattr(task, "_temp_keyfile_path"))
                delattr(task, "_temp_keyfile_path")

            return False

    async def _execute_break_lock(
        self,
        repository_path: str,
        passphrase: str,
        output_callback: Optional[Callable[[str], None]] = None,
        keyfile_content: Optional[str] = None,
    ) -> None:
        """Execute borg break-lock command to release stale repository locks"""
        try:
            if output_callback:
                output_callback(
                    "Running 'borg break-lock' to remove stale repository locks..."
                )

            async with secure_borg_command(
                base_command="borg break-lock",
                repository_path=repository_path,
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=[],
            ) as (command, env, _):
                process = await self.safe_executor.start_process(command, env)

                try:
                    result = await asyncio.wait_for(
                        self.safe_executor.monitor_process_output(
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
                        f"Successfully released lock on repository: {repository_path}"
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
                        f"Break-lock warning for {repository_path}: {error_msg}"
                    )

        except Exception as e:
            error_msg = f"Error executing break-lock: {str(e)}"
            if output_callback:
                output_callback(f"Warning: {error_msg}")
            logger.error(f"Break-lock error for repository {repository_path}: {e}")
            raise

    async def _execute_prune_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a prune task using JobExecutor"""
        try:
            params = task.parameters

            if job.repository_id is None:
                task.status = "failed"
                task.error = "Repository ID is missing"
                return False
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                task.status = "failed"
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = now_utc()
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = str(
                repo_data.get("passphrase") or params.get("passphrase") or ""
            )

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.safe_output_manager.add_output_line(
                        job.id, line, "stdout", progress
                    )
                )

            result = await self.safe_executor.execute_prune_task(
                repository_path=str(repository_path or ""),
                passphrase=passphrase,
                keep_within=str(params.get("keep_within"))
                if params.get("keep_within")
                else None,
                keep_secondly=int(str(params.get("keep_secondly") or 0))
                if params.get("keep_secondly")
                else None,
                keep_minutely=int(str(params.get("keep_minutely") or 0))
                if params.get("keep_minutely")
                else None,
                keep_hourly=int(str(params.get("keep_hourly") or 0))
                if params.get("keep_hourly")
                else None,
                keep_daily=int(str(params.get("keep_daily") or 0))
                if params.get("keep_daily")
                else None,
                keep_weekly=int(str(params.get("keep_weekly") or 0))
                if params.get("keep_weekly")
                else None,
                keep_monthly=int(str(params.get("keep_monthly") or 0))
                if params.get("keep_monthly")
                else None,
                keep_yearly=int(str(params.get("keep_yearly") or 0))
                if params.get("keep_yearly")
                else None,
                show_stats=bool(params.get("show_stats", True)),
                show_list=bool(params.get("show_list", False)),
                save_space=bool(params.get("save_space", False)),
                force_prune=bool(params.get("force_prune", False)),
                dry_run=bool(params.get("dry_run", False)),
                output_callback=task_output_callback,
            )

            # Set task status based on result
            task.return_code = result.return_code
            task.status = "completed" if result.return_code == 0 else "failed"
            task.completed_at = now_utc()
            if result.error:
                task.error = result.error

            return result.return_code == 0

        except Exception as e:
            logger.error(f"Exception in prune task: {str(e)}")
            task.status = "failed"
            task.return_code = -1
            task.error = f"Prune task failed: {str(e)}"
            task.completed_at = now_utc()
            return False

    async def _execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a repository check task"""
        try:
            params = task.parameters

            if job.repository_id is None:
                task.status = "failed"
                task.error = "Repository ID is missing"
                return False
            repo_data = await self._get_repository_data(job.repository_id)
            if not repo_data:
                task.status = "failed"
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = now_utc()
                return False

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = str(
                repo_data.get("passphrase") or params.get("passphrase") or ""
            )
            keyfile_content = repo_data.get("keyfile_content")
            if keyfile_content is not None and not isinstance(keyfile_content, str):
                keyfile_content = None  # Ensure it's str or None

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                asyncio.create_task(
                    self.safe_output_manager.add_output_line(
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

            if repository_path:
                additional_args.append(str(repository_path))

            async with secure_borg_command(
                base_command="borg check",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=additional_args,
            ) as (command, env, _):
                process = await self.safe_executor.start_process(command, env)
                self._processes[job.id] = process

                result = await self.safe_executor.monitor_process_output(
                    process, output_callback=task_output_callback
                )

                if job.id in self._processes:
                    del self._processes[job.id]

                task.return_code = result.return_code
                task.status = "completed" if result.return_code == 0 else "failed"
                task.completed_at = now_utc()

            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output:
                    for line in full_output.split("\n"):
                        if line.strip():
                            task.output_lines.append(line)
                            asyncio.create_task(
                                self.safe_output_manager.add_output_line(
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
            task.completed_at = now_utc()
            return False

    async def _execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a cloud sync task using JobExecutor"""
        params = task.parameters

        if job.repository_id is None:
            task.status = "failed"
            task.error = "Repository ID is missing"
            return False
        repo_data = await self._get_repository_data(job.repository_id)
        if not repo_data:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository not found"
            task.completed_at = now_utc()
            return False

        repository_path = repo_data.get("path") or params.get("repository_path")
        passphrase = str(repo_data.get("passphrase") or params.get("passphrase") or "")

        # Validate required parameters
        if not repository_path:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository path is required for cloud sync"
            task.completed_at = now_utc()
            return False

        if not passphrase:
            task.status = "failed"
            task.return_code = 1
            task.error = "Repository passphrase is required for cloud sync"
            task.completed_at = now_utc()
            return False

        def task_output_callback(line: str) -> None:
            task.output_lines.append(line)
            # Provide default progress since callback now only receives line
            progress: Dict[str, object] = {}
            asyncio.create_task(
                self.safe_output_manager.add_output_line(
                    job.id, line, "stdout", progress
                )
            )

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_OUTPUT,
                job_id=job.id,
                data={
                    "line": line,
                    "progress": None,  # No progress data
                    "task_index": task_index,
                },
            )

        # Get cloud sync config ID, defaulting to None if not configured
        cloud_sync_config_id_raw = params.get("cloud_sync_config_id")
        cloud_sync_config_id = (
            int(str(cloud_sync_config_id_raw or 0))
            if cloud_sync_config_id_raw is not None
            else None
        )

        # Handle skip case at caller level instead of inside executor
        if not cloud_sync_config_id:
            logger.info("No cloud backup configuration - skipping cloud sync")
            task.status = "completed"
            task.return_code = 0
            task.completed_at = now_utc()
            # Add output line for UI feedback
            task.output_lines.append("Cloud sync skipped - no configuration")
            asyncio.create_task(
                self.safe_output_manager.add_output_line(
                    job.id, "Cloud sync skipped - no configuration", "stdout", {}
                )
            )
            return True

        # Validate dependencies
        if not all(
            [
                self.dependencies.db_session_factory,
                self.dependencies.rclone_service,
                self.dependencies.encryption_service,
                self.dependencies.storage_factory,
                self.dependencies.provider_registry,
            ]
        ):
            task.status = "failed"
            task.error = "Missing required cloud sync dependencies"
            return False

        # Ensure required dependencies are available
        if not all(
            [
                self.dependencies.db_session_factory,
                self.dependencies.rclone_service,
                self.dependencies.encryption_service,
                self.dependencies.storage_factory,
                self.dependencies.provider_registry,
            ]
        ):
            raise RuntimeError(
                "Required dependencies for cloud sync task are not available"
            )

        # Type assertions after validation
        assert self.dependencies.db_session_factory is not None
        assert self.dependencies.rclone_service is not None
        assert self.dependencies.encryption_service is not None
        assert self.dependencies.storage_factory is not None
        assert self.dependencies.provider_registry is not None

        # Create a wrapper to convert context manager to direct session
        db_factory = self.dependencies.db_session_factory

        def session_factory() -> "Session":
            return db_factory().__enter__()

        result = await self.safe_executor.execute_cloud_sync_task(
            repository_path=str(repository_path or ""),
            cloud_sync_config_id=cloud_sync_config_id,
            db_session_factory=session_factory,
            rclone_service=self.dependencies.rclone_service,
            encryption_service=self.dependencies.encryption_service,
            storage_factory=self.dependencies.storage_factory,
            provider_registry=self.dependencies.provider_registry,
            output_callback=task_output_callback,
        )

        task.return_code = result.return_code
        task.status = "completed" if result.return_code == 0 else "failed"
        task.completed_at = now_utc()
        if result.error:
            task.error = result.error

        return result.return_code == 0

    async def _execute_notification_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a notification task using the new provider-based system"""
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
                from borgitory.models.database import NotificationConfig
                from borgitory.services.notifications.types import (
                    NotificationMessage,
                    NotificationType,
                    NotificationPriority,
                    NotificationConfig as NotificationConfigType,
                )

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

                # Use injected notification service
                if self.notification_service is None:
                    logger.error(
                        "NotificationService not available - ensure proper DI setup"
                    )
                    task.status = "failed"
                    task.return_code = 1
                    task.error = "NotificationService not available"
                    return False

                notification_service = self.notification_service

                # Load and decrypt configuration
                try:
                    decrypted_config = notification_service.load_config_from_storage(
                        config.provider, config.provider_config
                    )
                except Exception as e:
                    logger.error(f"Failed to load notification config: {e}")
                    task.status = "failed"
                    task.return_code = 1
                    task.error = f"Failed to load configuration: {str(e)}"
                    return False

                # Create notification config object
                notification_config = NotificationConfigType(
                    provider=config.provider,
                    config=dict(decrypted_config),  # Cast to dict[str, object]
                    name=config.name,
                    enabled=config.enabled,
                )

                title, message, notification_type_str, priority_value = (
                    self._generate_notification_content(job, task_index)
                )

                title_param = params.get("title")
                message_param = params.get("message")
                type_param = params.get("type")
                priority_param = params.get("priority")

                if title_param is not None:
                    title = str(title_param)
                if message_param is not None:
                    message = str(message_param)
                if type_param is not None:
                    notification_type_str = str(type_param)
                if priority_param is not None:
                    try:
                        priority_value = int(str(priority_param))
                    except (ValueError, TypeError):
                        pass

                try:
                    notification_type = NotificationType(
                        str(notification_type_str).lower()
                    )
                except ValueError:
                    notification_type = NotificationType.INFO

                try:
                    priority = NotificationPriority(
                        int(str(priority_value)) if priority_value else 0
                    )
                except ValueError:
                    priority = NotificationPriority.NORMAL

                notification_message = NotificationMessage(
                    title=str(title),
                    message=str(message),
                    notification_type=notification_type,
                    priority=priority,
                )

                task.output_lines.append(
                    f"Sending {config.provider} notification to {config.name}"
                )
                task.output_lines.append(f"Title: {title}")
                task.output_lines.append(f"Message: {message}")
                task.output_lines.append(f"Type: {notification_type.value}")
                task.output_lines.append(f"Priority: {priority.value}")

                self.safe_event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={
                        "line": f"Sending {config.provider} notification to {config.name}",
                        "task_index": task_index,
                    },
                )

                result = await notification_service.send_notification(
                    notification_config, notification_message
                )

                if result.success:
                    result_message = "✓ Notification sent successfully"
                    task.output_lines.append(result_message)
                    if result.message:
                        task.output_lines.append(f"Response: {result.message}")
                else:
                    result_message = f"✗ Failed to send notification: {result.error or result.message}"
                    task.output_lines.append(result_message)

                self.safe_event_broadcaster.broadcast_event(
                    EventType.JOB_OUTPUT,
                    job_id=job.id,
                    data={"line": result_message, "task_index": task_index},
                )

                task.status = "completed" if result.success else "failed"
                task.return_code = 0 if result.success else 1
                if not result.success:
                    task.error = result.error or "Failed to send notification"

                return result.success

        except Exception as e:
            logger.error(f"Error executing notification task: {e}")
            task.status = "failed"
            task.error = str(e)
            return False

    def _generate_notification_content(
        self, job: BorgJob, task_index: int
    ) -> tuple[str, str, str, int]:
        """
        Generate notification title, message, type, and priority based on job status.

        Args:
            job: The job to generate notification content for
            task_index: Current task index (for context)

        Returns:
            Tuple of (title, message, type, priority_value)
        """
        failed_tasks = [t for t in job.tasks if t.status == "failed"]
        completed_tasks = [t for t in job.tasks if t.status == "completed"]
        skipped_tasks = [t for t in job.tasks if t.status == "skipped"]

        critical_hook_failures = [
            t
            for t in failed_tasks
            if t.task_type == "hook" and t.parameters.get("critical_failure", False)
        ]
        backup_failures = [t for t in failed_tasks if t.task_type == "backup"]

        has_critical_failure = bool(critical_hook_failures or backup_failures)

        repository_name = "Unknown"
        if len(job.tasks) > 0 and "repository_name" in job.tasks[0].parameters:
            repository_name = str(job.tasks[0].parameters["repository_name"])

        if has_critical_failure:
            if critical_hook_failures:
                failed_hook_name = str(
                    critical_hook_failures[0].parameters.get(
                        "failed_critical_hook_name", "unknown"
                    )
                )
                title = "❌ Backup Job Failed - Critical Hook Error"
                message = (
                    f"Backup job for '{repository_name}' failed due to critical hook failure.\n\n"
                    f"Failed Hook: {failed_hook_name}\n"
                    f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                    f"Job ID: {job.id}"
                )
            else:
                title = "❌ Backup Job Failed - Backup Error"
                message = (
                    f"Backup job for '{repository_name}' failed during backup process.\n\n"
                    f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                    f"Job ID: {job.id}"
                )
            return title, message, "error", 1

        elif failed_tasks:
            failed_task_types = [t.task_type for t in failed_tasks]
            title = "⚠️ Backup Job Completed with Warnings"
            message = (
                f"Backup job for '{repository_name}' completed but some tasks failed.\n\n"
                f"Failed Tasks: {', '.join(failed_task_types)}\n"
                f"Tasks Completed: {len(completed_tasks)}, Skipped: {len(skipped_tasks)}, Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "warning", 0

        else:
            title = "✅ Backup Job Completed Successfully"
            message = (
                f"Backup job for '{repository_name}' completed successfully.\n\n"
                f"Tasks Completed: {len(completed_tasks)}"
                f"{f', Skipped: {len(skipped_tasks)}' if skipped_tasks else ''}"
                f", Total: {len(job.tasks)}\n"
                f"Job ID: {job.id}"
            )
            return title, message, "success", 0

    async def _execute_hook_task(
        self,
        job: BorgJob,
        task: BorgJobTask,
        task_index: int = 0,
        job_has_failed: bool = False,
    ) -> bool:
        """Execute a hook task"""
        if not self.dependencies.hook_execution_service:
            logger.error("Hook execution service not available")
            task.status = "failed"
            task.error = "Hook execution service not configured"
            return False

        try:
            task.status = "running"
            task.started_at = now_utc()

            hook_configs_data = task.parameters.get("hooks", [])
            hook_type = str(task.parameters.get("hook_type", "unknown"))

            if not hook_configs_data:
                logger.warning(
                    f"No hook configurations found for {hook_type} hook task"
                )
                task.status = "completed"
                task.return_code = 0
                task.completed_at = now_utc()
                return True

            from borgitory.services.hooks.hook_config import HookConfigParser

            try:
                hook_configs = HookConfigParser.parse_hooks_json(
                    hook_configs_data
                    if isinstance(hook_configs_data, str)
                    else str(hook_configs_data)
                )
            except Exception as e:
                logger.error(f"Failed to parse hook configurations: {e}")
                task.status = "failed"
                task.error = f"Invalid hook configuration: {str(e)}"
                task.return_code = 1
                task.completed_at = now_utc()
                return False

            hook_summary = await self.dependencies.hook_execution_service.execute_hooks(
                hooks=hook_configs,
                hook_type=hook_type,
                job_id=job.id,
                context={
                    "repository_id": str(job.repository_id)
                    if job.repository_id
                    else "unknown",
                    "task_index": str(task_index),
                    "job_type": str(job.job_type),
                },
                job_failed=job_has_failed,
            )

            error_messages = []

            for result in hook_summary.results:
                if result.output:
                    task.output_lines.append(
                        {
                            "text": f"[{result.hook_name}] {result.output}",
                            "timestamp": now_utc().isoformat(),
                        }
                    )

                if result.error:
                    task.output_lines.append(
                        {
                            "text": f"[{result.hook_name}] ERROR: {result.error}",
                            "timestamp": now_utc().isoformat(),
                        }
                    )

                if not result.success:
                    error_messages.append(
                        f"{result.hook_name}: {result.error or 'Unknown error'}"
                    )

            task.status = "completed" if hook_summary.all_successful else "failed"
            task.return_code = 0 if hook_summary.all_successful else 1
            task.completed_at = now_utc()

            if error_messages:
                if hook_summary.critical_failure:
                    task.error = (
                        f"Critical hook execution failed: {'; '.join(error_messages)}"
                    )
                else:
                    task.error = f"Hook execution failed: {'; '.join(error_messages)}"

            if hook_summary.critical_failure:
                task.parameters["critical_failure"] = True
                task.parameters["failed_critical_hook_name"] = (
                    hook_summary.failed_critical_hook_name
                )

            logger.info(
                f"Hook task {hook_type} completed with {len(hook_summary.results)} hooks "
                f"({'success' if hook_summary.all_successful else 'failure'})"
                f"{' (CRITICAL)' if hook_summary.critical_failure else ''}"
            )

            return hook_summary.all_successful

        except Exception as e:
            logger.error(f"Error executing hook task: {e}")
            task.status = "failed"
            task.error = str(e)
            task.return_code = 1
            task.completed_at = now_utc()
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
            elif task.task_type == "hook":
                return await self._execute_hook_task(
                    job, task, task_index, job_has_failed=False
                )
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

    def subscribe_to_events(self) -> Optional[asyncio.Queue[JobEvent]]:
        """Subscribe to job events"""
        if self.dependencies.event_broadcaster:
            return self.dependencies.event_broadcaster.subscribe_client()
        return None

    def unsubscribe_from_events(self, client_queue: asyncio.Queue[JobEvent]) -> bool:
        """Unsubscribe from job events"""
        if self.dependencies.event_broadcaster:
            return self.dependencies.event_broadcaster.unsubscribe_client(client_queue)
        return False

    async def stream_job_output(
        self, job_id: str
    ) -> AsyncGenerator[Dict[str, object], None]:
        """Stream job output"""
        if self.output_manager:
            async for output in self.safe_output_manager.stream_job_output(job_id):
                yield output
        else:
            return

    def get_job(self, job_id: str) -> Optional[BorgJob]:
        """Get job by ID"""
        return self.jobs.get(job_id)

    def list_jobs(self) -> Dict[str, BorgJob]:
        """List all jobs"""
        return self.jobs.copy()

    async def get_job_output(
        self, job_id: str
    ) -> AsyncGenerator[Dict[str, object], None]:
        """Get real-time job output"""
        if self.output_manager:
            async for output in self.safe_output_manager.stream_job_output(job_id):
                yield output
        else:
            return

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status not in ["running", "queued"]:
            return False

        if job_id in self._processes:
            process = self._processes[job_id]
            success = await self.safe_executor.terminate_process(process)
            if success:
                del self._processes[job_id]

        job.status = "cancelled"
        job.completed_at = now_utc()

        if self.database_manager:
            await self.database_manager.update_job_status(
                job_id, "cancelled", job.completed_at
            )

        self.safe_event_broadcaster.broadcast_event(
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

            self.safe_output_manager.clear_job_output(job_id)

            if job_id in self._processes:
                del self._processes[job_id]

            return True
        return False

    def get_queue_status(self) -> Dict[str, int]:
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
        return {}

    def get_active_jobs_count(self) -> int:
        """Get count of active (running/queued) jobs"""
        return len([j for j in self.jobs.values() if j.status in ["running", "queued"]])

    def get_job_status(self, job_id: str) -> Optional[Dict[str, object]]:
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

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict[str, object]:
        """Get job output stream data"""
        # Get output from output manager (don't require job to exist, just output)
        job_output = self.safe_output_manager.get_job_output(job_id)
        if job_output:
            # job_output.lines contains dict objects, not OutputLine objects
            lines = list(job_output.lines)
            if last_n_lines is not None and last_n_lines > 0:
                lines = lines[-last_n_lines:]
            return {
                "lines": lines,
                "progress": job_output.current_progress,
            }

        return {"lines": [], "progress": {}}

    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics (alias for get_queue_status)"""
        return self.get_queue_status()

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data by ID"""
        if hasattr(self, "database_manager") and self.database_manager:
            try:
                return await self.database_manager.get_repository_data(repository_id)
            except Exception as e:
                logger.error(
                    f"Error getting repository data from database manager: {e}"
                )

        return None

    async def stream_all_job_updates(self) -> AsyncGenerator[JobEvent, None]:
        """Stream all job updates via event broadcaster"""
        async for event in self.safe_event_broadcaster.stream_all_events():
            yield event

    async def shutdown(self) -> None:
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
            await self.safe_event_broadcaster.shutdown()

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
            started_at=now_utc(),
        )

        # Create a composite BorgJob (all jobs are now composite)
        job = BorgJob(
            id=job_id,
            command=[],  # External jobs don't have direct commands
            job_type="composite",  # All jobs are now composite
            status="running",
            started_at=now_utc(),
            repository_id=None,  # Can be set later if needed
            schedule=None,
            tasks=[main_task],  # Always has at least one task
        )

        self.jobs[job_id] = job

        # Initialize output tracking
        self.safe_output_manager.create_job_output(job_id)

        # Broadcast job started event
        self.safe_event_broadcaster.broadcast_event(
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
            job.completed_at = now_utc()

        # Update the main task status as well
        if job.tasks:
            main_task = job.tasks[0]  # First task is the main task
            main_task.status = status
            if error:
                main_task.error = error
            if return_code is not None:
                main_task.return_code = return_code
            if status in ["completed", "failed"]:
                main_task.completed_at = now_utc()

        # Broadcast status change event
        if old_status != status:
            if status == "completed":
                event_type = EventType.JOB_COMPLETED
            elif status == "failed":
                event_type = EventType.JOB_FAILED
            else:
                event_type = EventType.JOB_STATUS_CHANGED

            self.safe_event_broadcaster.broadcast_event(
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
            # Store output in dict format for backward compatibility
            main_task.output_lines.append({"text": output_line})

        # Also add output through output manager for streaming
        asyncio.create_task(
            self.safe_output_manager.add_output_line(job_id, output_line)
        )

        # Broadcast output event for real-time streaming
        self.safe_event_broadcaster.broadcast_event(
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


def get_default_job_manager_dependencies() -> JobManagerDependencies:
    """Get default job manager dependencies (production configuration)"""
    return JobManagerFactory.create_complete_dependencies()


def get_test_job_manager_dependencies(
    mock_subprocess: Optional[Callable[..., Any]] = None,
    mock_db_session: Optional[Callable[[], Any]] = None,
    mock_rclone_service: Optional[Any] = None,
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_subprocess=mock_subprocess,
        mock_db_session=mock_db_session,
        mock_rclone_service=mock_rclone_service,
    )


# Export all public classes and functions
__all__ = [
    "JobManager",
    "JobManagerConfig",
    "JobManagerDependencies",
    "JobManagerFactory",
    "BorgJob",
    "BorgJobTask",
    "get_default_job_manager_dependencies",
    "get_test_job_manager_dependencies",
]
