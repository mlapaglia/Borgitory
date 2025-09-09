import logging
from datetime import datetime, UTC
from typing import Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import DATABASE_URL
from app.models.database import Schedule
from app.models.enums import JobType
from app.utils.db_session import get_db_session

# Configure APScheduler logging only (don't override main basicConfig)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


async def execute_scheduled_backup(schedule_id: int):
    """Execute a scheduled backup"""
    logger.info(
        f"SCHEDULER: execute_scheduled_backup called for schedule_id: {schedule_id}"
    )

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
            logger.info("SCHEDULER: Creating composite job for scheduled backup")
            logger.info(f"  - repository: {repository.name}")
            logger.info(f"  - schedule: {schedule.name}")
            logger.info(f"  - source_path: {schedule.source_path}")
            logger.info(f"  - cloud_sync_config_id: {schedule.cloud_sync_config_id}")

            # Define the tasks for this composite job
            task_definitions = [
                {
                    "type": "backup",
                    "name": f"Backup {repository.name}",
                    "source_path": schedule.source_path,
                    "compression": "zstd",  # Default compression for scheduled backups
                    "dry_run": False,
                }
            ]

            # Add prune task if cleanup is configured
            if schedule.cleanup_config_id:
                from app.models.database import CleanupConfig

                cleanup_config = (
                    db.query(CleanupConfig)
                    .filter(
                        CleanupConfig.id == schedule.cleanup_config_id,
                        CleanupConfig.enabled,
                    )
                    .first()
                )

                if cleanup_config:
                    prune_task = {
                        "type": "prune",
                        "name": f"Clean up {repository.name}",
                        "dry_run": False,  # Don't dry run when chained after backup
                        "show_list": cleanup_config.show_list,
                        "show_stats": cleanup_config.show_stats,
                        "save_space": cleanup_config.save_space,
                    }

                    # Add retention parameters based on strategy
                    if (
                        cleanup_config.strategy == "simple"
                        and cleanup_config.keep_within_days
                    ):
                        prune_task["keep_within"] = (
                            f"{cleanup_config.keep_within_days}d"
                        )
                    elif cleanup_config.strategy == "advanced":
                        if cleanup_config.keep_daily:
                            prune_task["keep_daily"] = cleanup_config.keep_daily
                        if cleanup_config.keep_weekly:
                            prune_task["keep_weekly"] = cleanup_config.keep_weekly
                        if cleanup_config.keep_monthly:
                            prune_task["keep_monthly"] = cleanup_config.keep_monthly
                        if cleanup_config.keep_yearly:
                            prune_task["keep_yearly"] = cleanup_config.keep_yearly

                    task_definitions.append(prune_task)
                    logger.info("SCHEDULER: Added cleanup task to composite job")

            # Add check task if repository check is configured
            if schedule.check_config_id:
                from app.models.database import RepositoryCheckConfig

                check_config = (
                    db.query(RepositoryCheckConfig)
                    .filter(
                        RepositoryCheckConfig.id == schedule.check_config_id,
                        RepositoryCheckConfig.enabled,
                    )
                    .first()
                )

                if check_config:
                    check_task = {
                        "type": "check",
                        "name": f"Check {repository.name} ({check_config.name})",
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
                    task_definitions.append(check_task)
                    logger.info("SCHEDULER: Added check task to composite job")
            else:
                logger.info("SCHEDULER: No repository check configured")

            # Add cloud sync task if cloud backup is configured
            if schedule.cloud_sync_config_id:
                task_definitions.append({"type": "cloud_sync", "name": "Sync to Cloud"})
                logger.info("SCHEDULER: Added cloud sync task to composite job")
            else:
                logger.info("SCHEDULER: No cloud backup configured")

            # Create composite job
            from app.services.composite_job_manager import composite_job_manager
            
            job_id = await composite_job_manager.create_composite_job(
                job_type=JobType.SCHEDULED_BACKUP,
                task_definitions=task_definitions,
                repository=repository,
                schedule=schedule,
                cloud_sync_config_id=schedule.cloud_sync_config_id,
            )

            logger.info(
                f"SCHEDULER: Created composite job {job_id} with {len(task_definitions)} tasks"
            )

        except Exception as e:
            logger.error(
                f"SCHEDULER: Error creating composite job for schedule {schedule_id}: {str(e)}"
            )
            import traceback

            logger.error(f"SCHEDULER: Traceback: {traceback.format_exc()}")
            raise  # Re-raise so APScheduler marks the job as failed


class SchedulerService:
    def __init__(self):
        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": False, "max_instances": 1}

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults
        )
        self._running = False

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


# Global scheduler instance
# scheduler_service = SchedulerService()
