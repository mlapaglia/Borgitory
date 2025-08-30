import asyncio
from datetime import datetime
from typing import Dict, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy.orm import Session

from app.config import DATABASE_URL
from app.models.database import Repository, Job, Schedule, get_db
from app.services.borg_service import borg_service


class SchedulerService:
    def __init__(self):
        jobstores = {
            'default': SQLAlchemyJobStore(url=DATABASE_URL)
        }
        
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self.scheduler.add_listener(self._job_listener)
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        self._reload_schedules()
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
    
    def _job_listener(self, event):
        """Handle scheduler events"""
        if hasattr(event, 'job_id'):
            print(f"Scheduler event: {event} for job {event.job_id}")
    
    def _reload_schedules(self):
        """Reload all schedules from database"""
        db = next(get_db())
        try:
            schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
            for schedule in schedules:
                self.add_schedule(schedule, persist=False)
        finally:
            db.close()
    
    def add_schedule(self, schedule: Schedule, persist: bool = True) -> str:
        """Add a new scheduled backup job"""
        job_id = f"backup_schedule_{schedule.id}"
        
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            self.scheduler.add_job(
                func=self._execute_scheduled_backup,
                trigger=CronTrigger.from_crontab(schedule.cron_expression),
                args=[schedule.id],
                id=job_id,
                name=f"Backup {schedule.name}",
                replace_existing=True
            )
            
            if persist:
                db = next(get_db())
                try:
                    job = self.scheduler.get_job(job_id)
                    if job and job.next_run_time:
                        schedule.next_run = job.next_run_time
                        db.commit()
                finally:
                    db.close()
            
            return job_id
            
        except Exception as e:
            raise Exception(f"Failed to add schedule: {str(e)}")
    
    def remove_schedule(self, schedule_id: int):
        """Remove a scheduled backup job"""
        job_id = f"backup_schedule_{schedule_id}"
        
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
    
    def update_schedule(self, schedule: Schedule):
        """Update an existing scheduled backup job"""
        self.remove_schedule(schedule.id)
        if schedule.enabled:
            self.add_schedule(schedule)
    
    async def _execute_scheduled_backup(self, schedule_id: int):
        """Execute a scheduled backup"""
        db = next(get_db())
        try:
            schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not schedule:
                return
            
            repository = schedule.repository
            if not repository:
                return
            
            job = Job(
                repository_id=repository.id,
                type="scheduled_backup",
                status="running",
                started_at=datetime.utcnow()
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            
            schedule.last_run = datetime.utcnow()
            db.commit()
            
            try:
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
                        break
                    elif progress.get("type") == "started":
                        job.container_id = progress["container_id"]
                        db.commit()
                    elif progress.get("type") == "completed":
                        job.status = "completed" if progress["status"] == "success" else "failed"
                        break
                
                job.finished_at = datetime.utcnow()
                job.log_output = "\n".join(log_output)
                db.commit()
                
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
                job.finished_at = datetime.utcnow()
                db.commit()
                
        finally:
            db.close()
    
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