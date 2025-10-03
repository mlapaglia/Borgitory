import logging
from datetime import datetime
from dataclasses import dataclass
from borgitory.custom_types import ConfigDict
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, List, Optional, Any, cast
from sqlalchemy.orm import Session, joinedload

from borgitory.models.database import Repository, Job
from borgitory.models.schemas import BackupRequest, PruneRequest, CheckRequest
from borgitory.models.enums import JobType
from borgitory.models.job_results import (
    JobCreationResult,
    JobCreationError,
    JobCreationResponse,
    JobStatus,
    JobStatusError,
    JobStatusResponse,
    CompositeJobOutput,
    RegularJobOutput,
    JobOutputResponse,
    ManagerStats,
    QueueStats,
    JobStatusEnum,
    JobTypeEnum,
    JobStopResult,
    JobStopError,
    JobStopResponse,
)
from borgitory.protocols.job_protocols import JobManagerProtocol
from borgitory.services.task_definition_builder import TaskDefinitionBuilder

logger = logging.getLogger(__name__)


@dataclass
class BackupParams:
    """Parameters for backup tasks."""

    source_path: str
    compression: str
    dry_run: bool
    ignore_lock: bool
    patterns: List[str]


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
    ) -> JobCreationResponse:
        """Create a backup job with optional cleanup and check tasks"""
        repository = (
            self.db.query(Repository)
            .filter(Repository.id == backup_request.repository_id)
            .first()
        )

        if repository is None:
            return JobCreationError(
                error="Repository not found", error_code="REPOSITORY_NOT_FOUND"
            )

        builder = TaskDefinitionBuilder(self.db)

        # Convert patterns JSON to Borg command format
        patterns = []
        if backup_request.patterns:
            try:
                import json

                patterns_data = (
                    json.loads(backup_request.patterns)
                    if isinstance(backup_request.patterns, str)
                    else backup_request.patterns
                )

                if isinstance(patterns_data, list):
                    for pattern_data in patterns_data:
                        if (
                            isinstance(pattern_data, dict)
                            and pattern_data.get("name")
                            and pattern_data.get("expression")
                        ):
                            # Convert pattern to Borg format
                            pattern_type = pattern_data.get("pattern_type", "include")
                            style = pattern_data.get("style", "sh")
                            expression = pattern_data["expression"]

                            # Map pattern types to Borg prefixes
                            if pattern_type == "include":
                                prefix = "+"
                            elif pattern_type == "exclude":
                                prefix = "-"
                            elif pattern_type == "exclude_norec":
                                prefix = "!"
                            else:
                                prefix = "+"  # Default to include

                            # Build the pattern string
                            if style != "sh":  # sh is the default, no prefix needed
                                pattern = f"{prefix}{style}:{expression}"
                            else:
                                pattern = f"{prefix}{expression}"

                            patterns.append(pattern)
                            logger.info(
                                f"Converted pattern '{pattern_data['name']}' to Borg format: {pattern}"
                            )

            except Exception as e:
                logger.warning(f"Failed to parse patterns: {str(e)}")

        backup_params: ConfigDict = {
            "source_path": backup_request.source_path,
            "compression": backup_request.compression,
            "dry_run": backup_request.dry_run,
            "ignore_lock": backup_request.ignore_lock,
            "patterns": patterns,
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

        return JobCreationResult(job_id=job_id, status="started")

    async def create_prune_job(
        self, prune_request: PruneRequest
    ) -> JobCreationResponse:
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

        return JobCreationResult(job_id=job_id, status="started")

    async def create_check_job(
        self, check_request: CheckRequest
    ) -> JobCreationResponse:
        """Create a repository check job"""
        repository = (
            self.db.query(Repository)
            .filter(Repository.id == check_request.repository_id)
            .first()
        )

        if repository is None:
            return JobCreationError(
                error="Repository not found", error_code="REPOSITORY_NOT_FOUND"
            )

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

        return JobCreationResult(job_id=job_id, status="started")

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

    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """Get current job status and progress"""
        status_dict = self.job_manager.get_job_status(job_id)
        if status_dict is None:
            return JobStatusError(error="Job not found", job_id=job_id)

        # Convert dictionary to JobStatus object
        return JobStatus(
            id=str(status_dict["id"]),
            status=JobStatusEnum(str(status_dict["status"])),
            job_type=JobTypeEnum(str(status_dict["job_type"])),
            started_at=datetime.fromisoformat(str(status_dict["started_at"]))
            if status_dict["started_at"]
            else None,
            completed_at=datetime.fromisoformat(str(status_dict["completed_at"]))
            if status_dict["completed_at"]
            else None,
            return_code=cast(int, status_dict["return_code"])
            if status_dict["return_code"] is not None
            else None,
            error=str(status_dict["error"]) if status_dict["error"] else None,
            current_task_index=cast(int, status_dict["current_task_index"])
            if status_dict["current_task_index"] is not None
            else None,
            total_tasks=cast(int, status_dict["tasks"]) if status_dict["tasks"] else 0,
        )

    async def get_job_output(
        self, job_id: str, last_n_lines: int = 100
    ) -> JobOutputResponse:
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
                    # Ensure all lines are strings
                    current_task_output = [str(line) for line in lines]

            return CompositeJobOutput(
                job_id=job_id,
                job_type="composite",
                status=JobStatusEnum(job.status),
                current_task_index=job.current_task_index,
                total_tasks=len(job.tasks),
                current_task_output=current_task_output,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )
        else:
            # Get regular borg job output
            output_dict = await self.job_manager.get_job_output_stream(job_id)
            lines = cast(List[Any], output_dict.get("lines", []))
            if not isinstance(lines, list):
                lines = []
            # Convert dict lines to string lines if needed
            string_lines = []
            for line in lines:
                if isinstance(line, dict):
                    string_lines.append(line.get("message", str(line)))
                else:
                    string_lines.append(str(line))

            return RegularJobOutput(
                job_id=job_id,
                lines=string_lines,
                total_lines=len(string_lines),
                has_more=False,  # Could be enhanced to track this
            )

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

    async def stop_job(self, job_id: str) -> JobStopResponse:
        """Stop a running job, killing current task and skipping remaining tasks"""
        # Try to stop in JobManager first (for composite jobs)
        if len(job_id) > 10:  # Probably a UUID
            result = await self.job_manager.stop_job(job_id)

            if result["success"]:
                # Safely extract values with type casting
                tasks_skipped_val = result.get("tasks_skipped", 0)
                current_task_killed_val = result.get("current_task_killed", False)

                return JobStopResult(
                    job_id=job_id,
                    success=True,
                    message=str(result["message"]),
                    tasks_skipped=int(tasks_skipped_val)
                    if isinstance(tasks_skipped_val, (int, str))
                    else 0,
                    current_task_killed=bool(current_task_killed_val),
                )
            else:
                error_code_val = result.get("error_code")
                return JobStopError(
                    job_id=job_id,
                    error=str(result["error"]),
                    error_code=str(error_code_val)
                    if error_code_val is not None
                    else None,
                )

        # Try database job (fallback for older jobs)
        try:
            job = (
                self.db.query(Job)
                .options(joinedload(Job.repository))
                .filter(Job.id == job_id)
                .first()
            )
            if job:
                if job.status not in ["running", "queued"]:
                    return JobStopError(
                        job_id=job_id,
                        error=f"Cannot stop job in status: {job.status}",
                        error_code="INVALID_STATUS",
                    )

                # Update database status
                job.status = "stopped"
                job.finished_at = now_utc()
                job.error = "Manually stopped by user"
                self.db.commit()

                return JobStopResult(
                    job_id=job_id,
                    success=True,
                    message="Database job stopped successfully",
                    tasks_skipped=0,
                    current_task_killed=False,
                )
        except Exception as e:
            logger.error(f"Error stopping database job {job_id}: {e}")
            return JobStopError(
                job_id=job_id,
                error=f"Failed to stop job: {str(e)}",
                error_code="STOP_FAILED",
            )

        return JobStopError(
            job_id=job_id, error="Job not found", error_code="JOB_NOT_FOUND"
        )

    def get_manager_stats(self) -> ManagerStats:
        """Get JobManager statistics"""
        jobs = self.job_manager.jobs
        running_jobs = [job for job in jobs.values() if job.status == "running"]
        completed_jobs = [job for job in jobs.values() if job.status == "completed"]
        failed_jobs = [job for job in jobs.values() if job.status == "failed"]

        return ManagerStats(
            total_jobs=len(jobs),
            running_jobs=len(running_jobs),
            completed_jobs=len(completed_jobs),
            failed_jobs=len(failed_jobs),
            active_processes=len(self.job_manager._processes),
            running_job_ids=[job.id for job in running_jobs],
        )

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

    def get_queue_stats(self) -> QueueStats:
        """Get backup queue statistics"""
        stats_dict = self.job_manager.get_queue_stats()
        return QueueStats(
            pending=stats_dict.get("queued_backups", 0),
            running=stats_dict.get("running_backups", 0),
            completed=0,  # Not tracked in current implementation
            failed=0,  # Not tracked in current implementation
        )
