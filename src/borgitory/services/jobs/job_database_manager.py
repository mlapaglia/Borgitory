"""
Job Database Manager - Handles database operations with dependency injection
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, delete
from borgitory.protocols.job_database_manager_protocol import JobDatabaseManagerProtocol
from borgitory.services.jobs.job_models import TaskStatusEnum
from borgitory.models.job_results import JobStatusEnum
from borgitory.utils.datetime_utils import now_utc
from dataclasses import dataclass

if TYPE_CHECKING:
    from borgitory.services.jobs.job_models import BorgJobTask

logger = logging.getLogger(__name__)


@dataclass
class DatabaseJobData:
    """Data for creating/updating database job records"""

    id: uuid.UUID
    repository_id: int
    job_type: str
    status: JobStatusEnum
    started_at: datetime
    finished_at: Optional[datetime] = None
    return_code: Optional[int] = None
    output: Optional[str] = None
    error_message: Optional[str] = None
    cloud_sync_config_id: Optional[int] = None


class JobDatabaseManager(JobDatabaseManagerProtocol):
    """Manages database operations for jobs with dependency injection"""

    def __init__(
        self,
        async_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self.async_session_maker = async_session_maker

    async def create_database_job(
        self, job_data: DatabaseJobData
    ) -> Optional[uuid.UUID]:
        """Create a new job record in the database"""
        try:
            from borgitory.models.database import Job, StringUUID

            async with self.async_session_maker() as db:
                db_job = Job()
                db_job.id = StringUUID(job_data.id.hex)
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
                await db.commit()
                await db.refresh(db_job)

                logger.info(
                    f"Created database job record {db_job.id} for job {job_data.id}"
                )
                return db_job.id

        except Exception as e:
            logger.error(f"Failed to create database job record: {e}")
            return None

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatusEnum,
        finished_at: Optional[datetime] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update job status in database"""
        try:
            from borgitory.models.database import Job

            async with self.async_session_maker() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                db_job = result.scalar_one_or_none()

                if not db_job:
                    logger.warning(f"Database job not found for UUID {job_id}")
                    return False

                db_job.status = status
                if finished_at:
                    db_job.finished_at = finished_at
                if output is not None:
                    db_job.log_output = output
                if error_message is not None:
                    db_job.error = error_message

                await db.commit()

                logger.info(f"Updated database job {db_job.id} status to {status}")

                return True

        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False

    async def get_job_by_uuid(self, job_id: uuid.UUID) -> Optional[Dict[str, object]]:
        """Get job data by UUID"""
        try:
            from borgitory.models.database import Job

            async with self.async_session_maker() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                db_job = result.scalar_one_or_none()

                if not db_job:
                    return None

                return {
                    "id": db_job.id,
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
            logger.error(f"Failed to get job by UUID {job_id}: {e}")
            return None

    async def get_jobs_by_repository(
        self, repository_id: int, limit: int = 50, job_type: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """Get jobs for a specific repository"""
        try:
            from borgitory.models.database import Job

            async with self.async_session_maker() as db:
                query = select(Job).where(Job.repository_id == repository_id)

                if job_type:
                    query = query.where(Job.type == job_type)

                query = query.order_by(Job.started_at.desc()).limit(limit)
                result = await db.execute(query)
                jobs = result.scalars().all()

                return [
                    {
                        "id": job.id,
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

            async with self.async_session_maker() as db:
                result = await db.execute(
                    select(Repository).where(Repository.id == repository_id)
                )
                repo = result.scalar_one_or_none()

                if not repo:
                    return None

                return {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "passphrase": repo.get_passphrase(),
                    "keyfile_content": repo.get_keyfile_content(),
                    "cache_dir": repo.cache_dir,
                }

        except Exception as e:
            logger.error(f"Failed to get repository data for {repository_id}: {e}")
            return None

    async def get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data - public interface"""
        return await self._get_repository_data(repository_id)

    async def save_job_tasks(
        self, job_id: uuid.UUID, tasks: List["BorgJobTask"]
    ) -> bool:
        """Save task data for a job to the database"""
        try:
            from borgitory.models.database import Job, JobTask

            async with self.async_session_maker() as db:
                # Find the job by UUID
                result = await db.execute(select(Job).where(Job.id == job_id))
                db_job = result.scalar_one_or_none()
                if not db_job:
                    logger.warning(f"Job not found for UUID {job_id}")
                    return False

                # Clear existing tasks for this job
                await db.execute(delete(JobTask).where(JobTask.job_id == db_job.id))

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
                    (1 for task in tasks if task.status == TaskStatusEnum.COMPLETED), 0
                )

                await db.commit()
                logger.info(f"Saved {len(tasks)} tasks for job {job_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to save job tasks for {job_id}: {e}")
            return False

    async def get_job_statistics(self) -> Dict[str, object]:
        """Get job statistics"""
        try:
            from borgitory.models.database import Job
            from sqlalchemy import func

            async with self.async_session_maker() as db:
                # Total jobs by status
                result = await db.execute(
                    select(Job.status, func.count(Job.id)).group_by(Job.status)
                )
                status_counts = result.all()

                # Jobs by type
                result = await db.execute(
                    select(Job.type, func.count(Job.id)).group_by(Job.type)
                )
                type_counts = result.all()

                # Recent jobs (last 24 hours)
                from datetime import timedelta

                recent_cutoff = now_utc() - timedelta(hours=24)
                result = await db.execute(
                    select(func.count(Job.id)).where(Job.started_at >= recent_cutoff)
                )
                recent_jobs = result.scalar() or 0

                # Total jobs count
                result = await db.execute(select(func.count(Job.id)))
                total_jobs = result.scalar() or 0

                return {
                    "total_jobs": total_jobs,
                    "by_status": {status: count for status, count in status_counts},
                    "by_type": {job_type: count for job_type, count in type_counts},
                    "recent_jobs_24h": recent_jobs,
                }

        except Exception as e:
            logger.error(f"Failed to get job statistics: {e}")
            return {}
