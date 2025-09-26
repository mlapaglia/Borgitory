import logging
from borgitory.custom_types import ConfigDict
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload

from borgitory.models.database import Repository, Job
from borgitory.models.schemas import BackupRequest, PruneRequest, CheckRequest
from borgitory.models.enums import JobType
from borgitory.protocols.job_protocols import JobManagerProtocol
from borgitory.services.task_definition_builder import TaskDefinitionBuilder

logger = logging.getLogger(__name__)


class JobService:
    """
    Service for managing job operations.

    JobService is the single point of entry for all job creation and management.
    It orchestrates between JobManager (for job execution and monitoring) and
    specialized execution services like BackupService.
    """

    def __init__(
        self,
        db: Session,
        job_manager: JobManagerProtocol,
    ) -> None:
        self.db = db
        self.job_manager = job_manager

    async def create_backup_job(
        self, backup_request: BackupRequest, job_type: JobType
    ) -> Dict[str, object]:
        """Create a backup job with optional cleanup and check tasks"""
        repository = (
            self.db.query(Repository)
            .filter(Repository.id == backup_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Use TaskDefinitionBuilder to create all task definitions
        builder = TaskDefinitionBuilder(self.db)

        backup_params: ConfigDict = {
            "source_path": backup_request.source_path,
            "compression": backup_request.compression,
            "dry_run": backup_request.dry_run,
            "ignore_lock": backup_request.ignore_lock,
        }

        task_definitions = builder.build_task_list(
            repository_name=repository.name,
            include_backup=True,
            backup_params=backup_params,
            prune_config_id=backup_request.prune_config_id,
            check_config_id=backup_request.check_config_id,
            include_cloud_sync=backup_request.cloud_sync_config_id is not None,
            cloud_sync_config_id=backup_request.cloud_sync_config_id,
            notification_config_id=backup_request.notification_config_id,
            pre_job_hooks=backup_request.pre_job_hooks,
            post_job_hooks=backup_request.post_job_hooks,
        )

        # Create composite job using unified manager
        job_id = await self.job_manager.create_composite_job(
            job_type=job_type,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,  # No schedule for manual backups
            cloud_sync_config_id=backup_request.cloud_sync_config_id,
        )

        return {"job_id": job_id, "status": "started"}

    async def create_prune_job(self, prune_request: PruneRequest) -> Dict[str, object]:
        """Create a standalone prune job"""
        repository = (
            self.db.query(Repository)
            .filter(Repository.id == prune_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Use TaskDefinitionBuilder to create prune task
        builder = TaskDefinitionBuilder(self.db)
        task_def = builder.build_prune_task_from_request(prune_request, repository.name)
        task_definitions = [task_def]

        # Create composite job using unified manager
        job_id = await self.job_manager.create_composite_job(
            job_type=JobType.PRUNE,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,
        )

        return {"job_id": job_id, "status": "started"}

    async def create_check_job(self, check_request: CheckRequest) -> Dict[str, object]:
        """Create a repository check job"""
        repository = (
            self.db.query(Repository)
            .filter(Repository.id == check_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Use TaskDefinitionBuilder to create check task
        builder = TaskDefinitionBuilder(self.db)

        # Determine check parameters - either from borgitory.config or request
        if check_request.check_config_id:
            task_def = builder.build_check_task_from_config(
                check_request.check_config_id, repository.name
            )
            if task_def is None:
                raise ValueError("Check configuration not found or disabled")
        else:
            # Use custom parameters from request
            task_def = builder.build_check_task_from_request(
                check_request, repository.name
            )

        task_definitions = [task_def]

        # Create composite job using unified manager
        job_id = await self.job_manager.create_composite_job(
            job_type=JobType.CHECK,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,
        )

        return {"job_id": job_id, "status": "started"}

    def list_jobs(
        self, skip: int = 0, limit: int = 100, job_type: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """List database job records and active JobManager jobs"""
        # Get database jobs (legacy) with repository relationship loaded
        query = self.db.query(Job).options(joinedload(Job.repository))

        # Filter by type if provided
        if job_type:
            query = query.filter(Job.type == job_type)

        db_jobs = query.order_by(Job.id.desc()).offset(skip).limit(limit).all()

        # Convert to dict format and add JobManager jobs
        jobs_list = []

        # Add database jobs
        for job in db_jobs:
            repository_name = "Unknown"
            if job.repository_id and job.repository:
                repository_name = job.repository.name

            jobs_list.append(
                {
                    "id": job.id,
                    "job_id": str(job.id),  # Use primary key as job_id
                    "repository_id": job.repository_id,
                    "repository_name": repository_name,
                    "type": job.type,
                    "status": job.status,
                    "started_at": job.started_at.isoformat()
                    if job.started_at
                    else None,
                    "finished_at": job.finished_at.isoformat()
                    if job.finished_at
                    else None,
                    "error": job.error,
                    "log_output": job.log_output,
                    "source": "database",
                }
            )

        # Add active JobManager jobs
        for job_id, borg_job in self.job_manager.jobs.items():
            # Skip if this job is already in database
            existing_db_job = next((j for j in db_jobs if str(j.id) == job_id), None)
            if existing_db_job:
                continue

            # Try to find the repository name from command if possible
            repository_name = "Unknown"

            # Try to infer type from command
            job_type_inferred = JobType.from_command(borg_job.command or [])

            jobs_list.append(
                {
                    "id": f"jm_{job_id}",  # Prefix to distinguish from DB IDs
                    "job_id": job_id,
                    "repository_id": None,  # JobManager doesn't track this separately
                    "repository_name": repository_name,
                    "type": job_type_inferred,
                    "status": borg_job.status,
                    "started_at": borg_job.started_at.isoformat(),
                    "finished_at": borg_job.completed_at.isoformat()
                    if borg_job.completed_at
                    else None,
                    "error": borg_job.error,
                    "log_output": None,  # JobManager output is in-memory only
                    "source": "jobmanager",
                }
            )

        return jobs_list

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        """Get job details - supports both database IDs and JobManager IDs"""
        # Try to get from JobManager first (if it's a UUID format)
        if len(job_id) > 10:  # Probably a UUID
            status = self.job_manager.get_job_status(job_id)
            if status:
                return {
                    "id": f"jm_{job_id}",
                    "job_id": job_id,
                    "repository_id": None,
                    "type": "unknown",
                    "status": status["status"],
                    "started_at": status["started_at"],
                    "finished_at": status["completed_at"],
                    "error": status["error"],
                    "source": "jobmanager",
                }

        # Try database lookup
        try:
            job = (
                self.db.query(Job)
                .options(joinedload(Job.repository))
                .filter(Job.id == job_id)
                .first()
            )
            if job:
                repository_name = "Unknown"
                if job.repository_id and job.repository:
                    repository_name = job.repository.name

                return {
                    "id": job.id,
                    "job_id": str(job.id),  # Use primary key as job_id
                    "repository_id": job.repository_id,
                    "repository_name": repository_name,
                    "type": job.type,
                    "status": job.status,
                    "started_at": job.started_at.isoformat()
                    if job.started_at
                    else None,
                    "finished_at": job.finished_at.isoformat()
                    if job.finished_at
                    else None,
                    "error": job.error,
                    "log_output": job.log_output,
                    "source": "database",
                }
        except ValueError:
            pass

        return None

    async def get_job_status(self, job_id: str) -> Dict[str, object]:
        """Get current job status and progress"""
        status = self.job_manager.get_job_status(job_id)
        if status is None:
            return {"error": "Job not found"}
        return status

    async def get_job_output(
        self, job_id: str, last_n_lines: int = 100
    ) -> Dict[str, object]:
        """Get job output lines"""
        # Check if this is a composite job first - look in unified manager
        job = self.job_manager.jobs.get(job_id)
        if job and job.tasks:  # All jobs are composite now
            # Get current task output if job is running
            current_task_output = []
            if job.status == "running":
                current_task = job.get_current_task()
                if current_task:
                    lines = list(current_task.output_lines)
                    if last_n_lines:
                        lines = lines[-last_n_lines:]
                    current_task_output = lines

            return {
                "job_id": job_id,
                "job_type": "composite",
                "status": job.status,
                "current_task_index": job.current_task_index,
                "total_tasks": len(job.tasks),
                "current_task_output": current_task_output,
                "started_at": job.started_at.isoformat(),
                "completed_at": job.completed_at.isoformat()
                if job.completed_at
                else None,
            }
        else:
            # Get regular borg job output
            output = await self.job_manager.get_job_output_stream(job_id)
            return output

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        # Try to cancel in JobManager first
        if len(job_id) > 10:  # Probably a UUID
            success = await self.job_manager.cancel_job(job_id)
            if success:
                return True

        # Try database job
        try:
            job = (
                self.db.query(Job)
                .options(joinedload(Job.repository))
                .filter(Job.id == job_id)
                .first()
            )
            if job:
                # Update database status
                job.status = "cancelled"
                job.finished_at = now_utc()
                self.db.commit()
                return True
        except ValueError:
            pass

        return False

    def get_manager_stats(self) -> Dict[str, object]:
        """Get JobManager statistics"""
        jobs = self.job_manager.jobs
        running_jobs = [job for job in jobs.values() if job.status == "running"]
        completed_jobs = [job for job in jobs.values() if job.status == "completed"]
        failed_jobs = [job for job in jobs.values() if job.status == "failed"]

        return {
            "total_jobs": len(jobs),
            "running_jobs": len(running_jobs),
            "completed_jobs": len(completed_jobs),
            "failed_jobs": len(failed_jobs),
            "active_processes": len(self.job_manager._processes),
            "running_job_ids": [job.id for job in running_jobs],
        }

    def cleanup_completed_jobs(self) -> int:
        """Clean up completed jobs from JobManager memory"""
        cleaned = 0
        jobs_to_remove = []

        for job_id, job in self.job_manager.jobs.items():
            if job.status in ["completed", "failed"]:
                jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            self.job_manager.cleanup_job(job_id)
            cleaned += 1

        return cleaned

    def get_queue_stats(self) -> Dict[str, int]:
        """Get backup queue statistics"""
        return self.job_manager.get_queue_stats()
