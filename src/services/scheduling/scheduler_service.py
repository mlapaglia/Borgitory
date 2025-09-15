import logging
from datetime import datetime, UTC
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import DATABASE_URL
from models.database import Schedule
from models.schemas import BackupRequest
from models.enums import JobType
from utils.db_session import get_db_session
from services.jobs.job_service import JobService
from services.jobs.job_manager import JobManager

# Configure APScheduler logging only (don't override main basicConfig)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


# Global service instances for scheduler context
# These are created once and reused by the scheduler
_job_manager: Optional[JobManager] = None
_job_service_factory = None


def set_scheduler_dependencies(job_manager: JobManager, job_service_factory):
    """Set the dependencies for the scheduler context"""
    global _job_manager, _job_service_factory
    _job_manager = job_manager
    _job_service_factory = job_service_factory


async def execute_scheduled_backup(schedule_id: int):
    """Execute a scheduled backup using injected dependencies"""
    logger.info(
        f"SCHEDULER: execute_scheduled_backup called for schedule_id: {schedule_id}"
    )

    if _job_manager is None or _job_service_factory is None:
        logger.error("SCHEDULER: Dependencies not set. Call set_scheduler_dependencies first.")
        return

    with get_db_session() as db:
        logger.info(f"SCHEDULER: Looking up schedule {schedule_id}")
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        if not schedule:
            logger.error(f"SCHEDULER: Schedule {schedule_id} not found")
            return

        logger.info(
            f"SCHEDULER: Found schedule '{schedule.name}' for repository_id {schedule.repository_id}"
        )
        logger.info(
            f"SCHEDULER: Schedule details - cloud_sync_config_id: {schedule.cloud_sync_config_id}"
        )

        repository = schedule.repository
        if not repository:
            logger.error(f"SCHEDULER: Repository not found for schedule {schedule_id}")
            return

        logger.info(f"SCHEDULER: Found repository '{repository.name}'")

        # Update schedule last run
        logger.info("SCHEDULER: Updating schedule last run time")
        schedule.last_run = datetime.now(UTC)
        db.commit()

        try:
            logger.info("SCHEDULER: Creating scheduled backup via JobService")
            logger.info(f"  - repository: {repository.name}")
            logger.info(f"  - schedule: {schedule.name}")
            logger.info(f"  - source_path: {schedule.source_path}")
            logger.info(f"  - cloud_sync_config_id: {schedule.cloud_sync_config_id}")

            # Create a backup request object to use with JobService
            backup_request = BackupRequest(
                repository_id=repository.id,
                source_path=schedule.source_path,
                compression="zstd",  # Default compression for scheduled backups
                dry_run=False,
                cleanup_config_id=schedule.cleanup_config_id,
                check_config_id=schedule.check_config_id,
                cloud_sync_config_id=schedule.cloud_sync_config_id,
                notification_config_id=schedule.notification_config_id,
            )

            # Use injected JobService to create the backup job (same as manual backups)
            job_service = _job_service_factory(db, _job_manager)
            result = await job_service.create_backup_job(
                backup_request, JobType.SCHEDULED_BACKUP
            )
            job_id = result["job_id"]

            logger.info(
                f"SCHEDULER: Created scheduled backup job {job_id} via JobService"
            )

        except Exception as e:
            logger.error(
                f"SCHEDULER: Error creating job for schedule {schedule_id}: {str(e)}"
            )
            import traceback

            logger.error(f"SCHEDULER: Traceback: {traceback.format_exc()}")
            raise  # Re-raise so APScheduler marks the job as failed


class SchedulerService:
    def __init__(self, job_manager: Optional[JobManager] = None, job_service_factory=None):
        """
        Initialize the scheduler service with proper dependency injection.
        
        Args:
            job_manager: JobManager instance for handling jobs
            job_service_factory: Factory function to create JobService instances
        """
        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": False, "max_instances": 1}

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults
        )
        self._running = False
        
        # Set up dependencies for scheduler context
        self.job_manager = job_manager or JobManager()
        self.job_service_factory = job_service_factory or JobService
        
        # Set global dependencies for the execute_scheduled_backup function
        set_scheduler_dependencies(self.job_manager, self.job_service_factory)

    async def start(self):
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting APScheduler v3...")

        # Add event listeners
        self.scheduler.add_listener(
            self._handle_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self.scheduler.start()
        self._running = True

        # Load existing schedules
        await self._reload_schedules()

        logger.info("APScheduler v3 started successfully")

    async def stop(self):
        """Stop the scheduler gracefully"""
        if not self._running:
            return

        logger.info("Stopping APScheduler v3...")
        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("APScheduler v3 stopped successfully")

    def _handle_job_event(self, event):
        """Handle job execution events"""
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
        else:
            logger.info(f"Job {event.job_id} executed successfully")

    async def _reload_schedules(self):
        """Reload all schedules from database"""
        with get_db_session() as db:
            try:
                schedules = db.query(Schedule).filter(Schedule.enabled).all()
                for schedule in schedules:
                    await self._add_schedule_internal(
                        schedule.id,
                        schedule.name,
                        schedule.cron_expression,
                        persist=False,
                    )
            except Exception as e:
                logger.error(f"Error reloading schedules: {str(e)}")

    async def add_schedule(
        self, schedule_id: int, schedule_name: str, cron_expression: str
    ) -> str:
        """Add a new scheduled backup job"""
        if not self._running:
            raise RuntimeError("Scheduler is not running")

        return await self._add_schedule_internal(
            schedule_id, schedule_name, cron_expression, persist=True
        )

    async def _add_schedule_internal(
        self,
        schedule_id: int,
        schedule_name: str,
        cron_expression: str,
        persist: bool = True,
    ) -> str:
        """Internal method to add a schedule"""
        job_id = f"backup_schedule_{schedule_id}"

        try:
            # Validate cron expression
            try:
                trigger = CronTrigger.from_crontab(cron_expression)
            except ValueError as e:
                raise ValueError(
                    f"Invalid cron expression '{cron_expression}': {str(e)}"
                )

            # Remove existing job if it exists
            try:
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed existing job {job_id}")
            except Exception:
                pass  # Job doesn't exist, which is fine

            # Add the job
            self.scheduler.add_job(
                execute_scheduled_backup,
                trigger,
                args=[schedule_id],
                id=job_id,
                name=schedule_name,
                max_instances=1,
                misfire_grace_time=300,  # 5 minutes grace for missed jobs
            )

            logger.info(f"Added scheduled job {job_id} with cron '{cron_expression}'")

            # Update next run time in database
            if persist:
                await self._update_next_run_time(schedule_id, job_id)

            return job_id

        except Exception as e:
            logger.error(f"Failed to add schedule {schedule_id}: {str(e)}")
            raise Exception(f"Failed to add schedule: {str(e)}")

    async def _update_next_run_time(self, schedule_id: int, job_id: str):
        """Update the next run time in the database"""
        try:
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                with get_db_session() as db:
                    try:
                        schedule = (
                            db.query(Schedule)
                            .filter(Schedule.id == schedule_id)
                            .first()
                        )
                        if schedule:
                            schedule.next_run = job.next_run_time
                            logger.info(
                                f"Updated next run time for schedule {schedule_id}: {job.next_run_time}"
                            )
                    except Exception as e:
                        logger.error(f"Failed to update next run time: {str(e)}")
        except Exception as e:
            logger.error(f"Error updating next run time: {str(e)}")

    async def remove_schedule(self, schedule_id: int):
        """Remove a scheduled backup job"""
        if not self._running:
            return

        job_id = f"backup_schedule_{schedule_id}"

        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled job {job_id}")
        except Exception:
            logger.warning(f"Job {job_id} not found when trying to remove")

    async def update_schedule(
        self, schedule_id: int, schedule_name: str, cron_expression: str, enabled: bool
    ):
        """Update an existing scheduled backup job"""
        try:
            await self.remove_schedule(schedule_id)
            if enabled:
                await self.add_schedule(schedule_id, schedule_name, cron_expression)
                logger.info(f"Updated and enabled schedule {schedule_id}")
            else:
                logger.info(f"Schedule {schedule_id} disabled")
        except Exception as e:
            logger.error(f"Failed to update schedule {schedule_id}: {str(e)}")
            raise

    async def get_scheduled_jobs(self) -> List[Dict]:
        """Get all scheduled jobs with their next run times"""
        if not self._running:
            return []

        jobs = []
        try:
            for job in self.scheduler.get_jobs():
                if job.id.startswith("backup_schedule_"):
                    jobs.append(
                        {
                            "id": job.id,
                            "name": job.name
                            or f"Backup {job.id.replace('backup_schedule_', '')}",
                            "next_run": job.next_run_time,
                            "trigger": str(job.trigger),
                        }
                    )
        except Exception as e:
            logger.error(f"Error getting scheduled jobs: {str(e)}")
        return jobs
