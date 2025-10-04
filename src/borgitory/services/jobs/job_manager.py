"""
Job Manager - Consolidated modular job management system

This file consolidates the job management functionality from multiple files into a single,
clean architecture following the same pattern as other services in the application.
"""

import asyncio
import logging
import uuid
from typing import (
    Dict,
    Optional,
    List,
    AsyncGenerator,
    TYPE_CHECKING,
    Any,
)

from borgitory.models.job_results import JobStatusEnum
from borgitory.utils.datetime_utils import now_utc
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.services.jobs.job_models import (
    JobManagerConfig,
    JobManagerDependencies,
    BorgJob,
    BorgJobTask,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.services.jobs.job_queue_manager import QueuedJob, JobPriority
from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
)
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.jobs.broadcaster.job_event import JobEvent
from borgitory.services.jobs.task_executors import (
    BackupTaskExecutor,
    PruneTaskExecutor,
    CheckTaskExecutor,
    CloudSyncTaskExecutor,
    NotificationTaskExecutor,
    HookTaskExecutor,
)
from borgitory.services.jobs.external_job_manager import ExternalJobManager

if TYPE_CHECKING:
    from borgitory.models.database import Repository, Schedule
    from borgitory.protocols.command_protocols import ProcessExecutorProtocol

logger = logging.getLogger(__name__)


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

        # Initialize task executors
        self._init_task_executors()

        # Initialize external job manager
        self.external_job_manager = ExternalJobManager(
            self.jobs, self.output_manager, self.event_broadcaster
        )

        self._setup_callbacks()

    def _init_task_executors(self) -> None:
        """Initialize task executors with dependencies"""
        self.backup_executor = BackupTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )
        self.prune_executor = PruneTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )
        self.check_executor = CheckTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )
        self.cloud_sync_executor = CloudSyncTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )
        self.notification_executor = NotificationTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )
        self.hook_executor = HookTaskExecutor(
            self.executor, self.output_manager, self.event_broadcaster
        )

        # Inject repository data getter into executors
        for executor in [
            self.backup_executor,
            self.prune_executor,
            self.check_executor,
            self.cloud_sync_executor,
        ]:
            setattr(executor, "_get_repository_data", self._get_repository_data)

        # Inject dependencies into cloud sync executor
        setattr(
            self.cloud_sync_executor,
            "_get_dependencies",
            self._get_cloud_sync_dependencies,
        )

        # Inject notification service into notification executor
        setattr(
            self.notification_executor,
            "_get_notification_service",
            self._get_notification_service,
        )

        # Inject hook execution service into hook executor
        setattr(
            self.hook_executor,
            "_get_hook_execution_service",
            self._get_hook_execution_service,
        )

    @property
    def safe_executor(self) -> "ProcessExecutorProtocol":
        if self.executor is None:
            raise RuntimeError(
                "JobManager executor is None - ensure proper initialization"
            )
        return self.executor

    @property
    def safe_output_manager(self) -> Any:
        if self.output_manager is None:
            raise RuntimeError(
                "JobManager output_manager is None - ensure proper initialization"
            )
        return self.output_manager

    @property
    def safe_queue_manager(self) -> Any:
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
        job.status = JobStatusEnum.RUNNING
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
                job.status = JobStatusEnum.COMPLETED
            else:
                task.status = "failed"
                task.error = (
                    result.error
                    or f"Process failed with return code {result.return_code}"
                )
                job.status = JobStatusEnum.FAILED
                job.error = task.error

            job.return_code = result.return_code
            job.completed_at = now_utc()

            if result.error:
                task.error = result.error
                job.error = result.error

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == JobStatusEnum.COMPLETED
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = now_utc()
            job.status = JobStatusEnum.FAILED
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
            from borgitory.services.jobs.job_database_manager import DatabaseJobData

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
        job.status = JobStatusEnum.RUNNING

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

                # Execute the task based on its type using the appropriate executor
                try:
                    success = await self._execute_task_with_executor(
                        job, task, task_index
                    )

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
                        JobStatusEnum.FAILED
                        if (critical_task_failed or critical_hook_failed)
                        else JobStatusEnum.COMPLETED
                    )
                else:
                    job.status = JobStatusEnum.COMPLETED
            else:
                job.status = JobStatusEnum.FAILED

            job.completed_at = now_utc()

            # Update final job status
            if self.database_manager:
                await self.database_manager.update_job_status(
                    job.id, job.status, job.completed_at
                )

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == JobStatusEnum.COMPLETED
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={
                    "status": job.status,
                    "completed_at": job.completed_at.isoformat(),
                },
            )

        except Exception as e:
            job.status = JobStatusEnum.FAILED
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

    async def _execute_task_with_executor(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a task using the appropriate executor"""
        # For post-hooks, determine if job has failed so far
        job_has_failed = False
        if task.task_type == "hook":
            hook_type = task.parameters.get("hook_type", "unknown")
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

        # Route to appropriate executor
        if task.task_type == "backup":
            return await self.backup_executor.execute_backup_task(job, task, task_index)
        elif task.task_type == "prune":
            return await self.prune_executor.execute_prune_task(job, task, task_index)
        elif task.task_type == "check":
            return await self.check_executor.execute_check_task(job, task, task_index)
        elif task.task_type == "cloud_sync":
            return await self.cloud_sync_executor.execute_cloud_sync_task(
                job, task, task_index
            )
        elif task.task_type == "notification":
            return await self.notification_executor.execute_notification_task(
                job, task, task_index
            )
        elif task.task_type == "hook":
            return await self.hook_executor.execute_hook_task(
                job, task, task_index, job_has_failed
            )
        else:
            logger.warning(f"Unknown task type: {task.task_type}")
            task.status = "failed"
            task.return_code = 1
            task.error = f"Unknown task type: {task.task_type}"
            return False

    async def _execute_simple_job(
        self, job: BorgJob, command: List[str], env: Optional[Dict[str, str]] = None
    ) -> None:
        """Execute a simple single-command job (for test compatibility)"""
        job.status = JobStatusEnum.RUNNING

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

            job.status = (
                JobStatusEnum.COMPLETED
                if result.return_code == 0
                else JobStatusEnum.FAILED
            )
            job.return_code = result.return_code
            job.completed_at = now_utc()

            if result.error:
                job.error = result.error

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_COMPLETED
                if job.status == JobStatusEnum.COMPLETED
                else EventType.JOB_FAILED,
                job_id=job.id,
                data={"return_code": result.return_code, "status": job.status},
            )

        except Exception as e:
            job.status = JobStatusEnum.FAILED
            job.error = str(e)
            job.completed_at = now_utc()
            logger.error(f"Job {job.id} execution failed: {e}")

            self.safe_event_broadcaster.broadcast_event(
                EventType.JOB_FAILED, job_id=job.id, data={"error": str(e)}
            )

        finally:
            if job.id in self._processes:
                del self._processes[job.id]

    # Dependency injection methods for task executors
    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data by ID"""
        if hasattr(self, "database_manager") and self.database_manager:
            try:
                return await self.database_manager.get_repository_data(repository_id)
            except Exception as e:
                logger.error(
                    f"Error getting repository data from database manager: {e}"
                )

        return None

    async def _get_cloud_sync_dependencies(self) -> Optional[Dict[str, Any]]:
        """Get cloud sync dependencies"""
        return {
            "db_session_factory": self.dependencies.db_session_factory,
            "rclone_service": self.dependencies.rclone_service,
            "encryption_service": self.dependencies.encryption_service,
            "storage_factory": self.dependencies.storage_factory,
            "provider_registry": self.dependencies.provider_registry,
        }

    async def _get_notification_service(self) -> Optional[Any]:
        """Get notification service"""
        return self.notification_service

    async def _get_hook_execution_service(self) -> Optional[Any]:
        """Get hook execution service"""
        return self.dependencies.hook_execution_service

    def register_external_job(
        self, job_id: str, job_type: str = "backup", job_name: str = "External Backup"
    ) -> None:
        """Register an external job for monitoring purposes"""
        self.external_job_manager.register_external_job(job_id, job_type, job_name)

    def update_external_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        return_code: Optional[int] = None,
    ) -> None:
        """Update the status of an external job"""
        self.external_job_manager.update_external_job_status(
            job_id, status, error, return_code
        )

    def add_external_job_output(self, job_id: str, output_line: str) -> None:
        """Add output line to an external job"""
        self.external_job_manager.add_external_job_output(job_id, output_line)

    def unregister_external_job(self, job_id: str) -> None:
        """Unregister an external job"""
        self.external_job_manager.unregister_external_job(job_id)

    # Public API methods
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

        job.status = JobStatusEnum.CANCELLED
        job.completed_at = now_utc()

        if self.database_manager:
            await self.database_manager.update_job_status(
                job_id, JobStatusEnum.CANCELLED, job.completed_at
            )

        self.safe_event_broadcaster.broadcast_event(
            EventType.JOB_CANCELLED,
            job_id=job_id,
            data={"cancelled_at": job.completed_at.isoformat()},
        )

        return True

    async def stop_job(self, job_id: str) -> Dict[str, object]:
        """Stop a running job, killing current task and skipping remaining tasks"""
        job = self.jobs.get(job_id)
        if not job:
            return {
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }

        if job.status not in ["running", "queued"]:
            return {
                "success": False,
                "error": f"Cannot stop job in status: {job.status}",
                "error_code": "INVALID_STATUS",
            }

        current_task_killed = False
        tasks_skipped = 0

        # Kill current running process if exists
        if job_id in self._processes:
            process = self._processes[job_id]
            success = await self.safe_executor.terminate_process(process)
            if success:
                del self._processes[job_id]
                current_task_killed = True

        # For composite jobs, mark remaining tasks as skipped
        if job.job_type == "composite" and job.tasks:
            current_index = job.current_task_index

            # Mark current task as stopped if it was running
            if current_index < len(job.tasks):
                current_task = job.tasks[current_index]
                if current_task.status == "running":
                    current_task.status = "stopped"
                    current_task.completed_at = now_utc()
                    current_task.error = "Manually stopped by user"

            # Skip all remaining tasks (even critical/always_run ones since this is manual)
            for i in range(current_index + 1, len(job.tasks)):
                task = job.tasks[i]
                if task.status in ["pending", "queued"]:
                    task.status = "skipped"
                    task.completed_at = now_utc()
                    task.error = "Skipped due to manual job stop"
                    tasks_skipped += 1

        # Mark job as stopped
        job.status = JobStatusEnum.STOPPED
        job.completed_at = now_utc()
        job.error = "Manually stopped by user"

        # Update database
        if self.database_manager:
            await self.database_manager.update_job_status(
                job_id, "stopped", job.completed_at
            )

        # Broadcast stop event
        self.safe_event_broadcaster.broadcast_event(
            EventType.JOB_CANCELLED,  # Reuse existing event type
            job_id=job_id,
            data={
                "stopped_at": job.completed_at.isoformat(),
                "reason": "manual_stop",
                "tasks_skipped": tasks_skipped,
                "current_task_killed": current_task_killed,
            },
        )

        return {
            "success": True,
            "message": f"Job stopped successfully. {tasks_skipped} tasks skipped.",
            "tasks_skipped": tasks_skipped,
            "current_task_killed": current_task_killed,
        }

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
            "running": job.status == JobStatusEnum.RUNNING,
            "completed": job.status == JobStatusEnum.COMPLETED,
            "failed": job.status == JobStatusEnum.FAILED,
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
