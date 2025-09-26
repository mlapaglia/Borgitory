"""
Job Database Manager - Handles database operations with dependency injection
"""

import logging
from typing import Dict, List, Optional, Callable, TYPE_CHECKING, ContextManager
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from dataclasses import dataclass

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from borgitory.services.jobs.job_manager import BorgJobTask

logger = logging.getLogger(__name__)


@dataclass
class DatabaseJobData:
    """Data for creating/updating database job records"""

    job_uuid: str
    repository_id: int
    job_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    return_code: Optional[int] = None
    output: Optional[str] = None
    error_message: Optional[str] = None
    cloud_sync_config_id: Optional[int] = None


class JobDatabaseManager:
    """Manages database operations for jobs with dependency injection"""

    def __init__(
        self,
        db_session_factory: Optional[Callable[[], ContextManager["Session"]]] = None,
    ) -> None:
        self.db_session_factory = db_session_factory or self._default_db_session_factory

    def _default_db_session_factory(self) -> ContextManager["Session"]:
        """Default database session factory"""
        from borgitory.utils.db_session import get_db_session

        return get_db_session()

    async def create_database_job(self, job_data: DatabaseJobData) -> Optional[str]:
        """Create a new job record in the database"""
        try:
            from borgitory.models.database import Job

            with self.db_session_factory() as db:
                db_job = Job()
                db_job.id = job_data.job_uuid  # Use UUID as primary key
                db_job.repository_id = job_data.repository_id
                db_job.type = str(job_data.job_type)  # Convert JobType enum to string
                db_job.status = job_data.status
                db_job.started_at = job_data.started_at
                db_job.finished_at = job_data.finished_at
                db_job.log_output = job_data.output
                db_job.error = job_data.error_message
                db_job.container_id = None  # Explicitly set to None
                db_job.cloud_sync_config_id = job_data.cloud_sync_config_id
                db_job.prune_config_id = None  # Explicitly set to None
                db_job.check_config_id = None  # Explicitly set to None
                db_job.notification_config_id = None  # Explicitly set to None
                db_job.job_type = "composite"  # Set as composite since we have tasks
                db_job.total_tasks = 1  # Default total tasks
                db_job.completed_tasks = 0  # Default completed tasks

                db.add(db_job)
                db.commit()
                db.refresh(db_job)

                logger.info(
                    f"Created database job record {db_job.id} for job {job_data.job_uuid}"
                )
                return db_job.id  # Return UUID string

        except Exception as e:
            logger.error(f"Failed to create database job record: {e}")
            return None

    async def update_job_status(
        self,
        job_uuid: str,
        status: str,
        finished_at: Optional[datetime] = None,
        return_code: Optional[int] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update job status in database"""
        try:
            from borgitory.models.database import Job

            with self.db_session_factory() as db:
                db_job = db.query(Job).filter(Job.id == job_uuid).first()

                if not db_job:
                    logger.warning(f"Database job not found for UUID {job_uuid}")
                    return False

                # Update fields
                db_job.status = status
                if finished_at:
                    db_job.finished_at = finished_at
                if output is not None:
                    db_job.log_output = output
                if error_message is not None:
                    db_job.error = error_message

                db.commit()

                logger.info(f"Updated database job {db_job.id} status to {status}")

                return True

        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False

    async def get_job_by_uuid(self, job_uuid: str) -> Optional[Dict[str, object]]:
        """Get job data by UUID"""
        try:
            from borgitory.models.database import Job

            with self.db_session_factory() as db:
                db_job = db.query(Job).filter(Job.id == job_uuid).first()

                if not db_job:
                    return None

                return {
                    "id": db_job.id,
                    "job_uuid": db_job.id,  # Same as id now
                    "repository_id": db_job.repository_id,
                    "type": db_job.type,
                    "status": db_job.status,
                    "started_at": db_job.started_at.isoformat()
                    if db_job.started_at
                    else None,
                    "finished_at": db_job.finished_at.isoformat()
                    if db_job.finished_at
                    else None,
                    "output": db_job.log_output,
                    "error_message": db_job.error,
                    "cloud_sync_config_id": db_job.cloud_sync_config_id,
                }

        except Exception as e:
            logger.error(f"Failed to get job by UUID {job_uuid}: {e}")
            return None

    async def get_jobs_by_repository(
        self, repository_id: int, limit: int = 50, job_type: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """Get jobs for a specific repository"""
        try:
            from borgitory.models.database import Job

            with self.db_session_factory() as db:
                query = db.query(Job).filter(Job.repository_id == repository_id)

                if job_type:
                    query = query.filter(Job.type == job_type)

                jobs = query.order_by(Job.started_at.desc()).limit(limit).all()

                return [
                    {
                        "id": job.id,
                        "job_uuid": job.id,  # Same as id now
                        "type": job.type,
                        "status": job.status,
                        "started_at": job.started_at.isoformat()
                        if job.started_at
                        else None,
                        "finished_at": job.finished_at.isoformat()
                        if job.finished_at
                        else None,
                        "error_message": job.error,
                    }
                    for job in jobs
                ]

        except Exception as e:
            logger.error(f"Failed to get jobs for repository {repository_id}: {e}")
            return []

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data for cloud backup"""
        try:
            from borgitory.models.database import Repository

            with self.db_session_factory() as db:
                repo = (
                    db.query(Repository).filter(Repository.id == repository_id).first()
                )

                if not repo:
                    return None

                return {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "passphrase": repo.get_passphrase(),
                    "keyfile_content": repo.get_keyfile_content(),
                }

        except Exception as e:
            logger.error(f"Failed to get repository data for {repository_id}: {e}")
            return None

    async def get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data - public interface"""
        return await self._get_repository_data(repository_id)

    async def save_job_tasks(self, job_uuid: str, tasks: List["BorgJobTask"]) -> bool:
        """Save task data for a job to the database"""
        try:
            from borgitory.models.database import Job, JobTask

            with self.db_session_factory() as db:
                # Find the job by UUID
                db_job = db.query(Job).filter(Job.id == job_uuid).first()
                if not db_job:
                    logger.warning(f"Job not found for UUID {job_uuid}")
                    return False

                # Clear existing tasks for this job
                db.query(JobTask).filter(JobTask.job_id == db_job.id).delete()

                # Save each task
                for i, task in enumerate(tasks):
                    # Convert task output lines to string if needed
                    task_output = ""
                    if hasattr(task, "output_lines") and task.output_lines:
                        task_output = "\n".join(
                            [
                                (line.get("text", "") or "")
                                if isinstance(line, dict)
                                else str(line)
                                for line in task.output_lines
                            ]
                        )
                    elif hasattr(task, "output") and task.output:
                        task_output = task.output

                    db_task = JobTask()
                    db_task.job_id = db_job.id
                    db_task.task_type = task.task_type
                    db_task.task_name = task.task_name
                    db_task.status = task.status
                    db_task.started_at = getattr(task, "started_at", None)
                    db_task.completed_at = getattr(task, "completed_at", None)
                    db_task.output = task_output
                    db_task.error = getattr(task, "error", None)
                    db_task.return_code = getattr(task, "return_code", None)
                    db_task.task_order = i
                    db.add(db_task)

                # Update job task counts
                db_job.total_tasks = len(tasks)
                db_job.completed_tasks = sum(
                    (1 for task in tasks if task.status == "completed"), 0
                )

                db.commit()
                logger.info(f"Saved {len(tasks)} tasks for job {job_uuid}")
                return True

        except Exception as e:
            logger.error(f"Failed to save job tasks for {job_uuid}: {e}")
            return False

    async def get_job_statistics(self) -> Dict[str, object]:
        """Get job statistics"""
        try:
            from borgitory.models.database import Job
            from sqlalchemy import func

            with self.db_session_factory() as db:
                # Total jobs by status
                status_counts = (
                    db.query(Job.status, func.count(Job.id)).group_by(Job.status).all()
                )

                # Jobs by type
                type_counts = (
                    db.query(Job.type, func.count(Job.id)).group_by(Job.type).all()
                )

                # Recent jobs (last 24 hours)
                from datetime import timedelta

                recent_cutoff = now_utc() - timedelta(hours=24)
                recent_jobs = (
                    db.query(Job).filter(Job.started_at >= recent_cutoff).count()
                )

                return {
                    "total_jobs": db.query(Job).count(),
                    "by_status": {status: count for status, count in status_counts},
                    "by_type": {job_type: count for job_type, count in type_counts},
                    "recent_jobs_24h": recent_jobs,
                }

        except Exception as e:
            logger.error(f"Failed to get job statistics: {e}")
            return {}
