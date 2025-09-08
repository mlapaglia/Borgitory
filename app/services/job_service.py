import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session, joinedload

from app.models.database import (
    Repository,
    Job,
    CleanupConfig,
    RepositoryCheckConfig,
    NotificationConfig,
)
from app.models.schemas import BackupRequest, PruneRequest, CheckRequest
from app.models.enums import JobType
from app.services.job_manager_modular import ModularBorgJobManager, get_job_manager

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing job operations"""

    def __init__(self, job_manager: Optional[ModularBorgJobManager] = None):
        self.job_manager = job_manager or get_job_manager()

    async def create_backup_job(
        self, backup_request: BackupRequest, db: Session
    ) -> Dict[str, Any]:
        """Create a backup job with optional cleanup and check tasks"""
        repository = (
            db.query(Repository)
            .filter(Repository.id == backup_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Define the tasks for this manual backup job
        task_definitions = [
            {
                "type": "backup",
                "name": f"Backup {repository.name}",
                "source_path": backup_request.source_path,
                "compression": backup_request.compression,
                "dry_run": backup_request.dry_run,
            }
        ]

        # Add prune task if cleanup is configured
        if backup_request.cleanup_config_id:
            prune_task = await self._build_prune_task(
                backup_request.cleanup_config_id, repository.name, db
            )
            if prune_task:
                task_definitions.append(prune_task)

        # Add cloud sync task if cloud backup is configured
        if backup_request.cloud_sync_config_id:
            task_definitions.append({"type": "cloud_sync", "name": "Sync to Cloud"})

        # Add check task if repository check is configured
        if backup_request.check_config_id:
            check_task = await self._build_check_task(
                backup_request.check_config_id, repository.name, db
            )
            if check_task:
                task_definitions.append(check_task)

        # Add notification task if notification is configured
        if backup_request.notification_config_id:
            notification_task = await self._build_notification_task(
                backup_request.notification_config_id, repository.name, db
            )
            if notification_task:
                task_definitions.append(notification_task)

        # Create composite job using unified manager
        job_id = await self.job_manager.create_composite_job(
            job_type=JobType.MANUAL_BACKUP,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,  # No schedule for manual backups
            cloud_sync_config_id=backup_request.cloud_sync_config_id,
        )

        return {"job_id": job_id, "status": "started"}

    async def create_prune_job(
        self, prune_request: PruneRequest, db: Session
    ) -> Dict[str, Any]:
        """Create a standalone prune job"""
        repository = (
            db.query(Repository)
            .filter(Repository.id == prune_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Build task definition based on strategy
        task_def = {
            "type": "prune",
            "name": f"Prune {repository.name}",
            "dry_run": prune_request.dry_run,
            "show_list": prune_request.show_list,
            "show_stats": prune_request.show_stats,
            "save_space": prune_request.save_space,
            "force_prune": prune_request.force_prune,
        }

        # Add retention parameters based on strategy
        if prune_request.strategy == "simple" and prune_request.keep_within_days:
            task_def["keep_within"] = f"{prune_request.keep_within_days}d"
        elif prune_request.strategy == "advanced":
            if prune_request.keep_daily:
                task_def["keep_daily"] = prune_request.keep_daily
            if prune_request.keep_weekly:
                task_def["keep_weekly"] = prune_request.keep_weekly
            if prune_request.keep_monthly:
                task_def["keep_monthly"] = prune_request.keep_monthly
            if prune_request.keep_yearly:
                task_def["keep_yearly"] = prune_request.keep_yearly

        task_definitions = [task_def]

        # Import here to avoid circular imports
        from app.services.composite_job_manager import composite_job_manager

        # Create composite job
        job_id = await composite_job_manager.create_composite_job(
            job_type=JobType.PRUNE,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,
        )

        return {"job_id": job_id, "status": "started"}

    async def create_check_job(
        self, check_request: CheckRequest, db: Session
    ) -> Dict[str, Any]:
        """Create a repository check job"""
        repository = (
            db.query(Repository)
            .filter(Repository.id == check_request.repository_id)
            .first()
        )

        if repository is None:
            raise ValueError("Repository not found")

        # Determine check parameters - either from policy or custom
        if check_request.check_config_id:
            task_def = await self._build_check_task_from_config(
                check_request.check_config_id, repository.name, db
            )
        else:
            # Use custom parameters
            task_def = {
                "type": "check",
                "name": f"Check {repository.name}",
                "check_type": check_request.check_type,
                "verify_data": check_request.verify_data,
                "repair_mode": check_request.repair_mode,
                "save_space": check_request.save_space,
                "max_duration": check_request.max_duration,
                "archive_prefix": check_request.archive_prefix,
                "archive_glob": check_request.archive_glob,
                "first_n_archives": check_request.first_n_archives,
                "last_n_archives": check_request.last_n_archives,
            }

        task_definitions = [task_def]

        # Import here to avoid circular imports
        from app.services.composite_job_manager import composite_job_manager

        # Start the composite job
        job_id = await composite_job_manager.create_composite_job(
            job_type=JobType.CHECK,
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,
        )

        return {"job_id": job_id, "status": "started"}

    def list_jobs(
        self, skip: int = 0, limit: int = 100, job_type: str = None, db: Session = None
    ) -> List[Dict[str, Any]]:
        """List database job records and active JobManager jobs"""
        # Get database jobs (legacy) with repository relationship loaded
        query = db.query(Job).options(joinedload(Job.repository))

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
            job_type_inferred = JobType.from_command(borg_job.command)

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

    def get_job(self, job_id: str, db: Session) -> Optional[Dict[str, Any]]:
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
            db_job_id = int(job_id)
            job = (
                db.query(Job)
                .options(joinedload(Job.repository))
                .filter(Job.id == db_job_id)
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

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current job status and progress"""
        output = await self.job_manager.get_job_output_stream(job_id, last_n_lines=50)
        return output

    async def get_job_output(
        self, job_id: str, last_n_lines: int = 100
    ) -> Dict[str, Any]:
        """Get job output lines"""
        # Check if this is a composite job first - look in unified manager
        job = self.job_manager.jobs.get(job_id)
        if job and job.is_composite():
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
            output = await self.job_manager.get_job_output_stream(
                job_id, last_n_lines=last_n_lines
            )
            return output

    async def cancel_job(self, job_id: str, db: Session) -> bool:
        """Cancel a running job"""
        # Try to cancel in JobManager first
        if len(job_id) > 10:  # Probably a UUID
            success = await self.job_manager.cancel_job(job_id)
            if success:
                return True

        # Try database job
        try:
            db_job_id = int(job_id)
            job = (
                db.query(Job)
                .options(joinedload(Job.repository))
                .filter(Job.id == db_job_id)
                .first()
            )
            if job:
                # Update database status
                job.status = "cancelled"
                job.finished_at = datetime.now(UTC)
                db.commit()
                return True
        except ValueError:
            pass

        return False

    def get_manager_stats(self) -> Dict[str, Any]:
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

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get backup queue statistics"""
        return self.job_manager.get_queue_stats()

    async def _build_prune_task(
        self, cleanup_config_id: int, repository_name: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        """Build prune task definition from cleanup config"""
        cleanup_config = (
            db.query(CleanupConfig)
            .filter(
                CleanupConfig.id == cleanup_config_id,
                CleanupConfig.enabled,
            )
            .first()
        )

        if not cleanup_config:
            return None

        prune_task = {
            "type": "prune",
            "name": f"Clean up {repository_name}",
            "dry_run": False,  # Don't dry run when chained after backup
            "show_list": cleanup_config.show_list,
            "show_stats": cleanup_config.show_stats,
            "save_space": cleanup_config.save_space,
        }

        # Add retention parameters based on strategy
        if cleanup_config.strategy == "simple" and cleanup_config.keep_within_days:
            prune_task["keep_within"] = f"{cleanup_config.keep_within_days}d"
        elif cleanup_config.strategy == "advanced":
            if cleanup_config.keep_daily:
                prune_task["keep_daily"] = cleanup_config.keep_daily
            if cleanup_config.keep_weekly:
                prune_task["keep_weekly"] = cleanup_config.keep_weekly
            if cleanup_config.keep_monthly:
                prune_task["keep_monthly"] = cleanup_config.keep_monthly
            if cleanup_config.keep_yearly:
                prune_task["keep_yearly"] = cleanup_config.keep_yearly

        return prune_task

    async def _build_check_task(
        self, check_config_id: int, repository_name: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        """Build check task definition from check config"""
        check_config = (
            db.query(RepositoryCheckConfig)
            .filter(
                RepositoryCheckConfig.id == check_config_id,
                RepositoryCheckConfig.enabled,
            )
            .first()
        )

        if not check_config:
            return None

        return {
            "type": "check",
            "name": f"Check {repository_name} ({check_config.name})",
            "check_type": check_config.check_type,
            "verify_data": check_config.verify_data,
            "repair_mode": check_config.repair_mode,
            "save_space": check_config.save_space,
            "max_duration": check_config.max_duration,
            "archive_prefix": check_config.archive_prefix,
            "archive_glob": check_config.archive_glob,
            "first_n_archives": check_config.first_n_archives,
            "last_n_archives": check_config.last_n_archives,
        }

    async def _build_check_task_from_config(
        self, check_config_id: int, repository_name: str, db: Session
    ) -> Dict[str, Any]:
        """Build check task definition from existing check policy"""
        check_config = (
            db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.id == check_config_id)
            .first()
        )

        if not check_config:
            raise ValueError("Check policy not found")

        if not check_config.enabled:
            raise ValueError("Check policy is disabled")

        return {
            "type": "check",
            "name": f"Check {repository_name} ({check_config.name})",
            "check_type": check_config.check_type,
            "verify_data": check_config.verify_data,
            "repair_mode": check_config.repair_mode,
            "save_space": check_config.save_space,
            "max_duration": check_config.max_duration,
            "archive_prefix": check_config.archive_prefix,
            "archive_glob": check_config.archive_glob,
            "first_n_archives": check_config.first_n_archives,
            "last_n_archives": check_config.last_n_archives,
        }

    async def _build_notification_task(
        self, notification_config_id: int, repository_name: str, db: Session
    ) -> Optional[Dict[str, Any]]:
        """Build notification task definition from notification config"""
        notification_config = (
            db.query(NotificationConfig)
            .filter(
                NotificationConfig.id == notification_config_id,
                NotificationConfig.enabled,
            )
            .first()
        )

        if not notification_config:
            return None

        notification_task = {
            "type": "notification",
            "name": f"Send notification for {repository_name}",
            "provider": notification_config.provider,
            "notify_on_success": notification_config.notify_on_success,
            "notify_on_failure": notification_config.notify_on_failure,
            "config_id": notification_config_id,
        }

        return notification_task


# Global instance for dependency injection
job_service = JobService()
