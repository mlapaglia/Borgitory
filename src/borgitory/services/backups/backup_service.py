"""
BackupService - Simplified backup service that replaces JobManager + JobService

This service provides a direct, simplified interface for backup operations without
the complex job orchestration system. It handles:
- Direct backup execution
- Database persistence
- Event notifications
- Scheduling integration
"""

import logging
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, List, Optional, Union, Callable
from sqlalchemy.orm import Session

from borgitory.models.database import Repository, Job, JobTask
from borgitory.models.schemas import BackupRequest, PruneRequest
from borgitory.models.enums import JobType
from borgitory.services.backups.backup_executor import (
    BackupExecutor,
    BackupConfig,
    PruneConfig,
    BackupResult,
)

logger = logging.getLogger(__name__)


class BackupService:
    """
    Pure backup execution service.

    Handles backup, prune, and check operations execution only.
    Job creation and management is handled by JobService.
    """

    def __init__(
        self, db_session: Session, backup_executor: Optional[BackupExecutor] = None
    ) -> None:
        """
        Initialize the backup service.

        Args:
            db_session: SQLAlchemy database session
            backup_executor: Optional backup executor (creates default if None)
        """
        self.db = db_session
        self.executor = backup_executor or BackupExecutor()

    async def execute_backup(
        self,
        job: Job,
        backup_request: BackupRequest,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> BackupResult:
        """
        Execute a backup for an existing job.

        Args:
            job: Existing job record to execute backup for
            backup_request: Backup request with configuration
            output_callback: Optional callback for output lines

        Returns:
            BackupResult with execution details

        Raises:
            ValueError: If repository not found or configuration invalid
        """
        # Get repository
        repository = self._get_repository(backup_request.repository_id)
        if not repository:
            raise ValueError(f"Repository {backup_request.repository_id} not found")

        logger.info(f"Executing backup job {job.id} for repository {repository.name}")

        try:
            # Create backup configuration
            backup_config = BackupConfig(
                source_paths=[backup_request.source_path]
                if backup_request.source_path
                else ["/tmp"],
                compression=backup_request.compression or "zstd",
                dry_run=backup_request.dry_run or False,
                excludes=[],  # Can be extended from backup_request in the future
            )

            # Create backup task record
            backup_task = self._create_backup_task(job)

            # Prepare output callback that updates task and passes to external callback
            def combined_output_callback(line: str) -> None:
                self._handle_output_line(backup_task, line)
                if output_callback:
                    output_callback(line)

            # Execute backup
            result = await self.executor.execute_backup(
                repository=repository,
                config=backup_config,
                operation_id=job.id,
                output_callback=combined_output_callback,
            )

            # Update task with results
            self._update_task_from_result(backup_task, result)

            # Handle post-backup operations (prune, check, cloud sync, notifications)
            await self._handle_post_backup_operations(
                job, repository, backup_request, result.success
            )

            # Update final job status
            self._finalize_job(job)

            logger.info(f"Backup job {job.id} completed with status: {job.status}")
            return result

        except Exception as e:
            # Update job as failed
            job.status = "failed"
            job.error = str(e)
            job.finished_at = now_utc()
            self.db.commit()

            # Note: JobManager status updates are now handled by JobService

            logger.error(f"Backup job {job.id} failed: {e}")
            raise

    async def create_and_run_prune(self, prune_request: PruneRequest) -> str:
        """
        Create and execute a prune operation.

        Args:
            prune_request: Prune request with configuration

        Returns:
            Job ID of the created prune job
        """
        # Get repository
        repository = self._get_repository(prune_request.repository_id)
        if not repository:
            raise ValueError(f"Repository {prune_request.repository_id} not found")

        # Create job record
        job = self._create_job_record(repository, JobType.PRUNE, prune_request)

        logger.info(f"Starting prune job {job.id} for repository {repository.name}")

        # Note: JobManager registration is now handled by JobService

        try:
            # Create prune configuration
            prune_config = PruneConfig(
                keep_within=getattr(prune_request, "keep_within", None),
                keep_secondly=getattr(prune_request, "keep_secondly", None),
                keep_minutely=getattr(prune_request, "keep_minutely", None),
                keep_hourly=getattr(prune_request, "keep_hourly", None),
                keep_daily=getattr(prune_request, "keep_daily", None),
                keep_weekly=getattr(prune_request, "keep_weekly", None),
                keep_monthly=getattr(prune_request, "keep_monthly", None),
                keep_yearly=getattr(prune_request, "keep_yearly", None),
                dry_run=getattr(prune_request, "dry_run", False),
            )

            # Create prune task record
            prune_task = self._create_prune_task(job)

            # Execute prune
            result = await self.executor.execute_prune(
                repository=repository,
                config=prune_config,
                operation_id=job.id,
                output_callback=lambda line: self._handle_output_line(prune_task, line),
            )

            # Update task with results
            self._update_task_from_result(prune_task, result)

            # Update final job status
            self._finalize_job(job)

            logger.info(f"Prune job {job.id} completed with status: {job.status}")
            return job.id

        except Exception as e:
            # Update job as failed
            job.status = "failed"
            job.error = str(e)
            job.finished_at = now_utc()
            self.db.commit()

            # Note: JobManager status updates are now handled by JobService

            logger.error(f"Prune job {job.id} failed: {e}")
            raise

    def get_job_status(
        self, job_id: str
    ) -> Optional[
        Dict[str, Union[str, int, bool, None, List[Dict[str, Union[str, int, None]]]]]
    ]:
        """
        Get the status of a job.

        Args:
            job_id: ID of the job to check

        Returns:
            Dictionary with job status information or None if not found
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None

        # Get tasks for this job
        tasks = (
            self.db.query(JobTask)
            .filter(JobTask.job_id == job_id)
            .order_by(JobTask.task_order)
            .all()
        )

        return {
            "id": job.id,
            "status": job.status,
            "type": job.type,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error": job.error,
            "repository_id": job.repository_id,
            "tasks": [
                {
                    "type": task.task_type,
                    "name": task.task_name,
                    "status": task.status,
                    "started_at": task.started_at.isoformat()
                    if task.started_at
                    else None,
                    "completed_at": task.completed_at.isoformat()
                    if task.completed_at
                    else None,
                    "output": task.output,
                    "error": task.error,
                    "return_code": task.return_code,
                }
                for task in tasks
            ],
        }

    def list_recent_jobs(
        self, limit: int = 50
    ) -> List[
        Dict[str, Union[str, int, bool, None, List[Dict[str, Union[str, int, None]]]]]
    ]:
        """
        List recent jobs with their status.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job dictionaries
        """
        jobs = self.db.query(Job).order_by(Job.started_at.desc()).limit(limit).all()

        return [
            {
                "id": job.id,
                "status": job.status,
                "type": job.type,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "repository_id": job.repository_id,
                "repository_name": job.repository.name if job.repository else "Unknown",
            }
            for job in jobs
        ]

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: ID of the job to cancel

        Returns:
            True if job was cancelled, False otherwise
        """
        # Try to terminate the active operation
        success = await self.executor.terminate_operation(job_id)

        if success:
            # Update job status in database
            job = self.db.query(Job).filter(Job.id == job_id).first()
            if job and job.status == "running":
                job.status = "cancelled"
                job.finished_at = now_utc()
                job.error = "Job was cancelled by user"
                self.db.commit()
                logger.info(f"Job {job_id} was cancelled")

        return success

    def _get_repository(self, repository_id: int) -> Optional[Repository]:
        """Get repository by ID"""
        return self.db.query(Repository).filter(Repository.id == repository_id).first()

    def _create_job_record(
        self,
        repository: Repository,
        job_type: JobType,
        request: Union[BackupRequest, PruneRequest],
    ) -> Job:
        """Create a new job record in the database"""
        import uuid

        job = Job()
        job.id = str(uuid.uuid4())
        job.repository_id = repository.id
        job.type = job_type.value
        job.status = "running"
        job.started_at = now_utc()
        job.job_type = job_type.value  # For compatibility
        job.total_tasks = 1  # Will be updated if more tasks are added
        job.completed_tasks = 0

        # Add optional configurations
        if hasattr(request, "cloud_sync_config_id"):
            job.cloud_sync_config_id = request.cloud_sync_config_id
        if hasattr(request, "cleanup_config_id"):
            job.cleanup_config_id = request.cleanup_config_id
        if hasattr(request, "check_config_id"):
            job.check_config_id = request.check_config_id
        if hasattr(request, "notification_config_id"):
            job.notification_config_id = request.notification_config_id

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Created job record {job.id} for repository {repository.name}")
        return job

    def _create_backup_task(self, job: Job) -> JobTask:
        """Create a backup task record"""
        task = JobTask()
        task.job_id = job.id
        task.task_type = "backup"
        task.task_name = f"Backup {job.repository.name}"
        task.status = "running"
        task.started_at = now_utc()
        task.task_order = 0

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        return task

    def _create_prune_task(self, job: Job) -> JobTask:
        """Create a prune task record"""
        task = JobTask()
        task.job_id = job.id
        task.task_type = "prune"
        task.task_name = f"Prune {job.repository.name}"
        task.status = "running"
        task.started_at = now_utc()
        task.task_order = 0

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        return task

    def _handle_output_line(self, task: JobTask, line: str) -> None:
        """Handle a line of output from the backup process"""
        # Append to task output (we'll store as text)
        if not task.output:
            task.output = line
        else:
            task.output += "\n" + line

        # Note: Output forwarding to JobManager is now handled by JobService via output_callback

        # Commit periodically (every 10 lines to avoid too many commits)
        if task.output.count("\n") % 10 == 0:
            self.db.commit()

    def _update_task_from_result(self, task: JobTask, result: BackupResult) -> None:
        """Update task record with backup result"""
        task.status = "completed" if result.success else "failed"
        task.return_code = result.return_code
        task.completed_at = result.completed_at or now_utc()

        if result.error_message:
            task.error = result.error_message

        # Update output with all lines
        if result.output_lines:
            task.output = "\n".join(result.output_lines)

        self.db.commit()

    async def _handle_post_backup_operations(
        self,
        job: Job,
        repository: Repository,
        backup_request: BackupRequest,
        backup_success: bool,
    ) -> None:
        """Handle post-backup operations like prune, check, cloud sync, notifications"""
        # Only run post-backup operations if backup succeeded
        if not backup_success:
            logger.info(
                f"Skipping post-backup operations for job {job.id} due to backup failure"
            )
            return

        tasks_added = 0

        # TODO: Add prune task if cleanup_config_id is provided
        # TODO: Add check task if check_config_id is provided
        # TODO: Add cloud sync task if cloud_sync_config_id is provided
        # TODO: Add notification task if notification_config_id is provided

        # Update total task count
        if tasks_added > 0:
            job.total_tasks += tasks_added
            self.db.commit()

    def _finalize_job(self, job: Job) -> None:
        """Finalize job status based on task results"""
        # Get all tasks for this job
        tasks = self.db.query(JobTask).filter(JobTask.job_id == job.id).all()

        completed_tasks = [t for t in tasks if t.status == "completed"]
        failed_tasks = [t for t in tasks if t.status == "failed"]

        job.completed_tasks = len(completed_tasks)
        job.finished_at = now_utc()

        if failed_tasks:
            job.status = "failed"
            job.error = f"{len(failed_tasks)} task(s) failed"
        elif len(completed_tasks) == job.total_tasks:
            job.status = "completed"
        else:
            job.status = "partial"  # Some tasks might have been skipped

        self.db.commit()
        logger.info(f"Finalized job {job.id} with status: {job.status}")
