import logging
from datetime import datetime
import uuid
from borgitory.utils.datetime_utils import now_utc
import traceback
from typing import Dict, List, Union
from sqlalchemy import select

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from borgitory.config_module import DATABASE_URL
from borgitory.models.database import Schedule
from borgitory.models.schemas import BackupRequest, CompressionType
from borgitory.models.enums import JobType
from borgitory.models.job_results import JobCreationResult
from borgitory.services.jobs.job_service import JobService
from borgitory.protocols import JobManagerProtocol

logger = logging.getLogger(__name__)


async def execute_scheduled_backup(
    schedule_id: int,
    job_service: JobService,
) -> None:
    """Execute a scheduled backup using injected dependencies"""
    logger.info(
        f"SCHEDULER: execute_scheduled_backup called for schedule_id: {schedule_id}"
    )

    # Import here to avoid circular imports and pickling issues
    from borgitory.models.database import async_session_maker

    async with async_session_maker() as db:
        logger.info(f"SCHEDULER: Looking up schedule {schedule_id}")
        result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
        schedule = result.scalar_one_or_none()
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
        schedule.last_run = now_utc()
        await db.commit()

        try:
            logger.info("SCHEDULER: Creating scheduled backup via JobService")
            logger.info(f"  - repository: {repository.name}")
            logger.info(f"  - schedule: {schedule.name}")
            logger.info(f"  - source_path: {schedule.source_path}")
            logger.info(f"  - cloud_sync_config_id: {schedule.cloud_sync_config_id}")

            backup_request = BackupRequest(
                repository_id=repository.id,
                source_path=schedule.source_path,
                compression=CompressionType.ZSTD,
                dry_run=False,
                prune_config_id=schedule.prune_config_id,
                check_config_id=schedule.check_config_id,
                cloud_sync_config_id=schedule.cloud_sync_config_id,
                notification_config_id=schedule.notification_config_id,
                pre_job_hooks=schedule.pre_job_hooks,
                post_job_hooks=schedule.post_job_hooks,
                patterns=schedule.patterns,
            )

            backup_result = await job_service.create_backup_job(
                db, backup_request, JobType.SCHEDULED_BACKUP
            )

            if isinstance(backup_result, JobCreationResult):
                job_id = backup_result.job_id
                logger.info(
                    f"SCHEDULER: Created scheduled backup job {job_id} via JobService"
                )
            else:
                logger.error(
                    f"SCHEDULER: Failed to create backup job: {backup_result.error}"
                )
                return

        except Exception as e:
            logger.error(
                f"SCHEDULER: Error creating job for schedule {schedule_id}: {str(e)}"
            )

            logger.error(f"SCHEDULER: Traceback: {traceback.format_exc()}")
            raise


class SchedulerService:
    def __init__(
        self,
        job_manager: JobManagerProtocol,
        job_service: JobService,
    ) -> None:
        """
        Initialize the scheduler service with proper dependency injection.

        Args:
            job_manager: JobManager instance for handling jobs
            job_service: JobService instance
        """
        jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": False, "max_instances": 1}

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults
        )
        self._running = False

        self.job_manager = job_manager
        self.job_service = job_service

    async def start(self) -> None:
        """Start the scheduler"""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting APScheduler v3...")

        self.scheduler.add_listener(
            self._handle_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self.scheduler.start()
        self._running = True

        await self._reload_schedules()

        logger.info("APScheduler v3 started successfully")

    async def stop(self) -> None:
        """Stop the scheduler gracefully"""
        if not self._running:
            return

        logger.info("Stopping APScheduler v3...")
        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("APScheduler v3 stopped successfully")

    def _handle_job_event(self, event: object) -> None:
        """Handle job execution events"""
        if (
            hasattr(event, "exception")
            and hasattr(event, "job_id")
            and getattr(event, "exception")
        ):
            logger.error(
                f"Job {getattr(event, 'job_id')} failed: {getattr(event, 'exception')}"
            )
        elif (
            hasattr(event, "code")
            and hasattr(event, "job_id")
            and getattr(event, "code") == EVENT_JOB_ERROR
        ):
            logger.error(f"Job {getattr(event, 'job_id')} failed")
        elif hasattr(event, "job_id"):
            logger.info(f"Job {getattr(event, 'job_id')} executed successfully")

    async def _reload_schedules(self) -> None:
        """Reload all schedules from database"""
        from borgitory.models.database import async_session_maker

        async with async_session_maker() as db:
            try:
                result = await db.execute(select(Schedule).where(Schedule.enabled))
                schedules = result.scalars().all()
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
            try:
                trigger = CronTrigger.from_crontab(cron_expression)
            except ValueError as e:
                raise ValueError(
                    f"Invalid cron expression '{cron_expression}': {str(e)}"
                )

            try:
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed existing job {job_id}")
            except Exception:
                pass

            self.scheduler.add_job(
                execute_scheduled_backup,
                trigger,
                args=[schedule_id, self.job_service],
                id=job_id,
                name=schedule_name,
                max_instances=1,
                misfire_grace_time=300,
            )

            logger.info(f"Added scheduled job {job_id} with cron '{cron_expression}'")

            if persist:
                await self._update_next_run_time(schedule_id, job_id)

            return job_id

        except Exception as e:
            logger.error(f"Failed to add schedule {schedule_id}: {str(e)}")
            raise Exception(f"Failed to add schedule: {str(e)}")

    async def _update_next_run_time(self, schedule_id: int, job_id: str) -> None:
        """Update the next run time in the database"""
        try:
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                from borgitory.models.database import async_session_maker

                async with async_session_maker() as db:
                    try:
                        result = await db.execute(
                            select(Schedule).where(Schedule.id == schedule_id)
                        )
                        schedule = result.scalar_one_or_none()
                        if schedule:
                            schedule.next_run = job.next_run_time
                            logger.info(
                                f"Updated next run time for schedule {schedule_id}: {job.next_run_time}"
                            )
                    except Exception as e:
                        logger.error(f"Failed to update next run time: {str(e)}")
        except Exception as e:
            logger.error(f"Error updating next run time: {str(e)}")

    async def remove_schedule(self, schedule_id: int) -> None:
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
    ) -> None:
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

    async def run_schedule_once(self, schedule_id: int, schedule_name: str) -> str:
        """Run a schedule immediately as a one-time job"""
        if not self._running:
            raise RuntimeError("Scheduler is not running")

        job_id = str(uuid.uuid4())

        try:
            # Schedule the job to run immediately using DateTrigger
            self.scheduler.add_job(
                execute_scheduled_backup,
                DateTrigger(run_date=now_utc()),
                args=[schedule_id, self.job_service],
                id=job_id,
                name=f"Manual run: {schedule_name}",
                max_instances=1,
                misfire_grace_time=60,  # Shorter grace time for one-time jobs
            )

            logger.info(f"Added one-time job {job_id} for schedule {schedule_id}")
            return job_id

        except Exception as e:
            logger.error(
                f"Failed to add one-time job for schedule {schedule_id}: {str(e)}"
            )
            raise Exception(f"Failed to schedule manual run: {str(e)}")

    async def get_scheduled_jobs(self) -> List[Dict[str, Union[str, datetime, None]]]:
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
