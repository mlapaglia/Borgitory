import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from sqlalchemy.orm import Session

from app.config import DATABASE_URL
from app.models.database import Repository, Job, Schedule, get_db
from app.services.borg_service import borg_service

# Configure APScheduler logging
logging.getLogger('apscheduler').setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def execute_scheduled_backup(schedule_id: int):
    """Execute a scheduled backup - standalone function following APScheduler best practices"""
    logger.info(f"Starting scheduled backup for schedule_id: {schedule_id}")
    
    db = next(get_db())
    try:
        schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return
        
        repository = schedule.repository
        if not repository:
            logger.error(f"Repository not found for schedule {schedule_id}")
            return
        
        # Create job record
        job = Job(
            repository_id=repository.id,
            type="scheduled_backup",
            status="running",
            started_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Update schedule last run
        schedule.last_run = datetime.utcnow()
        db.commit()
        
        logger.info(f"Created job {job.id} for scheduled backup of repository {repository.name}")
        
        try:
            # Run backup synchronously using asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def run_backup():
                log_output = []
                async for progress in borg_service.create_backup(
                    repository=repository,
                    source_path="/data",  # Default path for scheduled backups
                    compression="zstd"
                ):
                    if progress.get("type") == "log":
                        log_output.append(progress["message"])
                    elif progress.get("type") == "error":
                        job.status = "failed"
                        job.error = progress["message"]
                        logger.error(f"Backup error for job {job.id}: {progress['message']}")
                        break
                    elif progress.get("type") == "started":
                        job.container_id = progress["container_id"]
                        db.commit()
                    elif progress.get("type") == "completed":
                        job.status = "completed" if progress["status"] == "success" else "failed"
                        logger.info(f"Backup completed for job {job.id} with status: {job.status}")
                        break
                
                job.finished_at = datetime.utcnow()
                job.log_output = "\n".join(log_output)
                return job.status
            
            final_status = loop.run_until_complete(run_backup())
            loop.close()
            
            db.commit()
            logger.info(f"Scheduled backup job {job.id} finished with status: {final_status}")
            
        except Exception as e:
            logger.error(f"Error during scheduled backup job {job.id}: {str(e)}")
            job.status = "failed"
            job.error = str(e)
            job.finished_at = datetime.utcnow()
            db.commit()
            
    except Exception as e:
        logger.error(f"Fatal error in scheduled backup for schedule {schedule_id}: {str(e)}")
    finally:
        db.close()


class SchedulerService:
    def __init__(self):
        jobstores = {
            'default': SQLAlchemyJobStore(url=DATABASE_URL)
        }
        
        job_defaults = {
            'coalesce': False,  # Don't coalesce multiple missed jobs
            'max_instances': 1,  # Only one instance of a job at a time
            'misfire_grace_time': 60  # 60 seconds grace time for missed jobs
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, 
            job_defaults=job_defaults
        )
        
        # Add event listeners for better monitoring
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed, EVENT_JOB_MISSED)
    
    def start(self):
        """Start the scheduler following best practices"""
        if not self.scheduler.running:
            logger.info("Starting APScheduler...")
            self.scheduler.start()
            self._reload_schedules()
            logger.info("APScheduler started successfully")
        else:
            logger.warning("APScheduler is already running")
    
    def stop(self):
        """Stop the scheduler gracefully"""
        if self.scheduler.running:
            logger.info("Stopping APScheduler...")
            self.scheduler.shutdown(wait=True)
            logger.info("APScheduler stopped successfully")
    
    def _job_executed(self, event):
        """Handle successful job execution"""
        logger.info(f"Job {event.job_id} executed successfully")
    
    def _job_error(self, event):
        """Handle job execution errors"""
        logger.error(f"Job {event.job_id} crashed: {event.exception}")
    
    def _job_missed(self, event):
        """Handle missed job executions"""
        logger.warning(f"Job {event.job_id} was scheduled to run at {event.scheduled_run_time} but was missed")
    
    def _reload_schedules(self):
        """Reload all schedules from database"""
        db = next(get_db())
        try:
            schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
            for schedule in schedules:
                self.add_schedule(schedule.id, schedule.name, schedule.cron_expression, persist=False)
        finally:
            db.close()
    
    def add_schedule(self, schedule_id: int, schedule_name: str, cron_expression: str, persist: bool = True) -> str:
        """Add a new scheduled backup job following APScheduler best practices"""
        job_id = f"backup_schedule_{schedule_id}"
        
        try:
            # Validate cron expression first
            try:
                CronTrigger.from_crontab(cron_expression)
            except ValueError as e:
                raise ValueError(f"Invalid cron expression '{cron_expression}': {str(e)}")
            
            # Remove existing job if it exists
            if self.scheduler.get_job(job_id):
                logger.info(f"Removing existing job {job_id}")
                self.scheduler.remove_job(job_id)
            
            # Add job with proper configuration
            self.scheduler.add_job(
                func=execute_scheduled_backup,
                trigger=CronTrigger.from_crontab(cron_expression),
                args=[schedule_id],  # Only pass serializable arguments
                id=job_id,
                name=f"Backup {schedule_name}",
                replace_existing=True,
                # Additional APScheduler best practice settings
                coalesce=False,  # Don't combine missed executions
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=300  # 5 minutes grace for missed jobs
            )
            
            logger.info(f"Added scheduled job {job_id} with cron '{cron_expression}'")
            
            # Update next run time in database
            if persist:
                db = next(get_db())
                try:
                    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
                    if schedule:
                        job = self.scheduler.get_job(job_id)
                        if job and job.next_run_time:
                            schedule.next_run = job.next_run_time
                            db.commit()
                            logger.info(f"Updated next run time for schedule {schedule_id}: {job.next_run_time}")
                except Exception as e:
                    logger.error(f"Failed to update next run time: {str(e)}")
                finally:
                    db.close()
            
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to add schedule {schedule_id}: {str(e)}")
            raise Exception(f"Failed to add schedule: {str(e)}")
    
    def remove_schedule(self, schedule_id: int):
        """Remove a scheduled backup job"""
        job_id = f"backup_schedule_{schedule_id}"
        
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed scheduled job {job_id}")
            else:
                logger.warning(f"Job {job_id} not found when trying to remove")
        except Exception as e:
            logger.error(f"Failed to remove schedule {schedule_id}: {str(e)}")
    
    def update_schedule(self, schedule_id: int, schedule_name: str, cron_expression: str, enabled: bool):
        """Update an existing scheduled backup job"""
        try:
            self.remove_schedule(schedule_id)
            if enabled:
                self.add_schedule(schedule_id, schedule_name, cron_expression)
                logger.info(f"Updated and enabled schedule {schedule_id}")
            else:
                logger.info(f"Schedule {schedule_id} disabled")
        except Exception as e:
            logger.error(f"Failed to update schedule {schedule_id}: {str(e)}")
            raise
    
    def get_scheduled_jobs(self) -> List[Dict]:
        """Get all scheduled jobs with their next run times"""
        jobs = []
        for job in self.scheduler.get_jobs():
            if job.id.startswith("backup_schedule_"):
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time,
                    "trigger": str(job.trigger)
                })
        return jobs


scheduler_service = SchedulerService()