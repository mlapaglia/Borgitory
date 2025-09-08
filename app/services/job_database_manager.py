"""
Job Database Manager - Handles database operations with dependency injection
"""

import logging
from typing import Dict, List, Optional, Callable, Any, TYPE_CHECKING
from datetime import datetime, UTC
from dataclasses import dataclass

if TYPE_CHECKING:
    pass

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
    schedule_id: Optional[int] = None


class JobDatabaseManager:
    """Manages database operations for jobs with dependency injection"""

    def __init__(
        self,
        db_session_factory: Optional[Callable] = None,
        cloud_backup_coordinator: Optional[Any] = None,
    ):
        self.db_session_factory = db_session_factory or self._default_db_session_factory
        self.cloud_backup_coordinator = cloud_backup_coordinator

    def _default_db_session_factory(self):
        """Default database session factory"""
        from app.utils.db_session import get_db_session

        return get_db_session()

    async def create_database_job(self, job_data: DatabaseJobData) -> Optional[int]:
        """Create a new job record in the database"""
        try:
            from app.models.database import Job

            with self.db_session_factory() as db:
                db_job = Job(
                    job_uuid=job_data.job_uuid,
                    repository_id=job_data.repository_id,
                    type=job_data.job_type,
                    status=job_data.status,
                    started_at=job_data.started_at,
                    finished_at=job_data.finished_at,
                    return_code=job_data.return_code,
                    output=job_data.output,
                    error_message=job_data.error_message,
                    cloud_sync_config_id=job_data.cloud_sync_config_id,
                    schedule_id=job_data.schedule_id,
                )

                db.add(db_job)
                db.commit()
                db.refresh(db_job)

                logger.info(
                    f"Created database job record {db_job.id} for job {job_data.job_uuid}"
                )
                return db_job.id

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
            from app.models.database import Job

            with self.db_session_factory() as db:
                db_job = db.query(Job).filter(Job.job_uuid == job_uuid).first()

                if not db_job:
                    logger.warning(f"Database job not found for UUID {job_uuid}")
                    return False

                # Update fields
                db_job.status = status
                if finished_at:
                    db_job.finished_at = finished_at
                if return_code is not None:
                    db_job.return_code = return_code
                if output is not None:
                    db_job.output = output
                if error_message is not None:
                    db_job.error_message = error_message

                db.commit()

                logger.info(f"Updated database job {db_job.id} status to {status}")

                # Trigger cloud backup if job completed successfully
                if (
                    status == "completed"
                    and return_code == 0
                    and db_job.cloud_sync_config_id
                    and self.cloud_backup_coordinator
                ):
                    await self._trigger_cloud_backup(db_job)

                return True

        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            return False

    async def get_job_by_uuid(self, job_uuid: str) -> Optional[Dict[str, Any]]:
        """Get job data by UUID"""
        try:
            from app.models.database import Job

            with self.db_session_factory() as db:
                db_job = db.query(Job).filter(Job.job_uuid == job_uuid).first()

                if not db_job:
                    return None

                return {
                    "id": db_job.id,
                    "job_uuid": db_job.job_uuid,
                    "repository_id": db_job.repository_id,
                    "type": db_job.type,
                    "status": db_job.status,
                    "started_at": db_job.started_at.isoformat()
                    if db_job.started_at
                    else None,
                    "finished_at": db_job.finished_at.isoformat()
                    if db_job.finished_at
                    else None,
                    "return_code": db_job.return_code,
                    "output": db_job.output,
                    "error_message": db_job.error_message,
                    "cloud_sync_config_id": db_job.cloud_sync_config_id,
                    "schedule_id": db_job.schedule_id,
                }

        except Exception as e:
            logger.error(f"Failed to get job by UUID {job_uuid}: {e}")
            return None

    async def get_jobs_by_repository(
        self, repository_id: int, limit: int = 50, job_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get jobs for a specific repository"""
        try:
            from app.models.database import Job

            with self.db_session_factory() as db:
                query = db.query(Job).filter(Job.repository_id == repository_id)

                if job_type:
                    query = query.filter(Job.type == job_type)

                jobs = query.order_by(Job.started_at.desc()).limit(limit).all()

                return [
                    {
                        "id": job.id,
                        "job_uuid": job.job_uuid,
                        "type": job.type,
                        "status": job.status,
                        "started_at": job.started_at.isoformat()
                        if job.started_at
                        else None,
                        "finished_at": job.finished_at.isoformat()
                        if job.finished_at
                        else None,
                        "return_code": job.return_code,
                        "error_message": job.error_message,
                    }
                    for job in jobs
                ]

        except Exception as e:
            logger.error(f"Failed to get jobs for repository {repository_id}: {e}")
            return []

    async def cleanup_old_jobs(
        self, older_than_days: int = 30, keep_count: int = 10
    ) -> int:
        """Clean up old job records"""
        try:
            from app.models.database import Job
            from datetime import timedelta

            cutoff_date = datetime.now(UTC) - timedelta(days=older_than_days)
            cleaned_count = 0

            with self.db_session_factory() as db:
                # For each repository, keep at least keep_count recent jobs
                repositories = db.query(Job.repository_id).distinct().all()

                for (repo_id,) in repositories:
                    # Get jobs older than cutoff date
                    old_jobs_query = (
                        db.query(Job)
                        .filter(Job.repository_id == repo_id)
                        .filter(Job.started_at < cutoff_date)
                        .order_by(Job.started_at.desc())
                    )

                    # Keep at least keep_count jobs
                    total_jobs = (
                        db.query(Job).filter(Job.repository_id == repo_id).count()
                    )

                    if total_jobs > keep_count:
                        # Skip the most recent keep_count jobs
                        jobs_to_delete = old_jobs_query.offset(keep_count).all()

                        for job in jobs_to_delete:
                            db.delete(job)
                            cleaned_count += 1

                if cleaned_count > 0:
                    db.commit()
                    logger.info(f"Cleaned up {cleaned_count} old job records")

                return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup old jobs: {e}")
            return 0

    async def _trigger_cloud_backup(self, db_job) -> None:
        """Trigger cloud backup for completed backup job"""
        try:
            if not self.cloud_backup_coordinator:
                logger.debug("No cloud backup coordinator configured")
                return

            logger.info(
                f"Triggering cloud backup for job {db_job.id} "
                f"with cloud_sync_config_id {db_job.cloud_sync_config_id}"
            )

            # Get repository data
            repository_data = await self._get_repository_data(db_job.repository_id)
            if not repository_data:
                logger.error(f"Repository not found for job {db_job.id}")
                return

            # Trigger cloud backup through coordinator
            await self.cloud_backup_coordinator.trigger_cloud_backup(
                repository_data=repository_data,
                cloud_sync_config_id=db_job.cloud_sync_config_id,
                source_job_id=db_job.id,
            )

        except Exception as e:
            logger.error(f"Failed to trigger cloud backup for job {db_job.id}: {e}")

    async def _get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get repository data for cloud backup"""
        try:
            from app.models.database import Repository

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
                }

        except Exception as e:
            logger.error(f"Failed to get repository data for {repository_id}: {e}")
            return None

    async def get_repository_data(self, repository_id: int) -> Optional[Dict[str, Any]]:
        """Get repository data - public interface"""
        return await self._get_repository_data(repository_id)

    async def get_job_statistics(self) -> Dict[str, Any]:
        """Get job statistics"""
        try:
            from app.models.database import Job
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

                recent_cutoff = datetime.now(UTC) - timedelta(hours=24)
                recent_jobs = (
                    db.query(Job).filter(Job.started_at >= recent_cutoff).count()
                )

                return {
                    "total_jobs": db.query(Job).count(),
                    "by_status": dict(status_counts),
                    "by_type": dict(type_counts),
                    "recent_jobs_24h": recent_jobs,
                }

        except Exception as e:
            logger.error(f"Failed to get job statistics: {e}")
            return {}
