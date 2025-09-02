"""
Recovery service for handling crashed or interrupted backup jobs.

This service handles cleanup when the application restarts after being
shut down or crashed while backup jobs were running.
"""

import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from app.models.database import get_db, Job, Repository
from app.utils.security import build_secure_borg_command
import asyncio

logger = logging.getLogger(__name__)


class RecoveryService:
    """Service to recover from application crashes during backup operations"""
    
    async def recover_stale_jobs(self):
        """
        Find composite jobs that were running when the app was shut down and clean them up.
        This should be called on application startup.
        
        Note: We only handle composite jobs since all backup operations now use the composite job system.
        Legacy jobs (repository operations like scan, init) are not critical and will be cleaned up naturally.
        """
        logger.info("🔧 Starting recovery: checking for composite jobs interrupted by shutdown...")
        
        # Only recover composite jobs - they handle actual backup operations
        await self.recover_composite_jobs()
        
        logger.info("✅ Recovery complete - all interrupted backup jobs cancelled and locks released")
    
    
    async def _release_repository_lock(self, repository: Repository):
        """Use borg break-lock to release any stale locks on a repository"""
        try:
            logger.info(f"🔓 Attempting to release lock on repository: {repository.name}")
            
            # Build borg break-lock command
            command, env = build_secure_borg_command(
                base_command="borg break-lock",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=[]
            )
            
            # Execute the break-lock command with a timeout
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                
                if process.returncode == 0:
                    logger.info(f"✅ Successfully released lock on repository: {repository.name}")
                else:
                    # Log the error but don't fail - lock might not exist
                    stderr_text = stderr.decode() if stderr else "No error details"
                    logger.warning(f"⚠️  Break-lock returned {process.returncode} for {repository.name}: {stderr_text}")
                    
            except asyncio.TimeoutError:
                logger.warning(f"⚠️  Break-lock timed out for repository: {repository.name}")
                process.kill()
                
        except Exception as e:
            logger.error(f"❌ Error releasing lock for repository {repository.name}: {e}")
    
    async def recover_composite_jobs(self):
        """
        Recover composite jobs that may be stuck in running state.
        This handles the new composite job system.
        """
        try:
            # Import here to avoid circular imports
            from app.services.composite_job_manager import composite_job_manager
            
            logger.info("🔧 Checking for stale composite jobs...")
            
            # Get all jobs from the composite job manager
            stale_composite_jobs = []
            
            for job_id, job_info in composite_job_manager.jobs.items():
                if job_info.status == 'running':
                    # Any running job is stale after app restart since all processes were killed
                    stale_composite_jobs.append((job_id, job_info))
            
            if stale_composite_jobs:
                logger.info(f"🔍 Found {len(stale_composite_jobs)} stale composite jobs")
                
                db = next(get_db())
                try:
                    for job_id, job_info in stale_composite_jobs:
                        logger.info(f"🔧 Cancelling stale composite job {job_id} - was running since {job_info.started_at}")
                        
                        # Release repository lock if it was a backup job
                        if job_info.repository:
                            logger.info(f"🔓 Releasing repository lock for: {job_info.repository.name}")
                            await self._release_repository_lock(job_info.repository)
                        
                        # Mark composite job as failed (cancelled due to app restart)
                        job_info.status = 'failed'
                        job_info.completed_at = datetime.now()
                        
                        # Mark all running tasks as failed too
                        for task in job_info.tasks:
                            if task.status in ['pending', 'in_progress', 'running']:
                                task.status = 'failed'
                                task.completed_at = datetime.now()
                                task.error = "Task cancelled on startup - job was interrupted by application shutdown"
                                logger.info(f"  ✅ Task '{task.task_name}' marked as failed")
                        
                        # Update database record
                        db_job = db.query(Job).filter(Job.id == job_info.db_job_id).first()
                        if db_job:
                            db_job.status = 'failed'
                            db_job.completed_at = datetime.now()
                            db_job.error = f"Error: Job cancelled on startup - was running when application shut down (started: {db_job.started_at})"
                            
                            # Also update database task records
                            from app.models.database import JobTask
                            db_tasks = db.query(JobTask).filter(JobTask.job_id == db_job.id).all()
                            for db_task in db_tasks:
                                if db_task.status in ['pending', 'running', 'in_progress']:
                                    db_task.status = 'failed'
                                    db_task.completed_at = datetime.now()
                                    db_task.error = "Task cancelled on startup - job was interrupted by application shutdown"
                    
                    db.commit()
                    logger.info("✅ All stale composite jobs recovered")
                    
                finally:
                    db.close()
            else:
                logger.info("✅ No stale composite jobs found")
                
        except Exception as e:
            logger.error(f"❌ Error recovering composite jobs: {e}")


# Global instance
recovery_service = RecoveryService()