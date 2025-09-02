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
        Find jobs that were running when the app was shut down and clean them up.
        This should be called on application startup.
        """
        logger.info("🔧 Starting recovery process for stale backup jobs...")
        
        db = next(get_db())
        try:
            # Find jobs that are still marked as running
            stale_jobs = self._find_stale_jobs(db)
            
            if not stale_jobs:
                logger.info("✅ No stale jobs found - recovery complete")
                return
            
            logger.info(f"🔍 Found {len(stale_jobs)} stale jobs to recover")
            
            # Process each stale job
            for job in stale_jobs:
                await self._recover_job(job, db)
            
            logger.info("✅ Recovery process completed")
            
        except Exception as e:
            logger.error(f"❌ Error during recovery process: {e}")
        finally:
            db.close()
    
    def _find_stale_jobs(self, db: Session) -> List[Job]:
        """Find jobs that are marked as running but likely stale"""
        
        # Consider jobs stale if they've been running for more than this duration
        # without any updates (assuming app was restarted)
        stale_threshold = datetime.now() - timedelta(minutes=5)
        
        stale_jobs = db.query(Job).filter(
            Job.status == 'running',
            Job.started_at < stale_threshold  # Been running for a while
        ).all()
        
        logger.info(f"🔍 Checking for jobs running longer than {stale_threshold}")
        
        return stale_jobs
    
    async def _recover_job(self, job: Job, db: Session):
        """Recover a single stale job"""
        try:
            logger.info(f"🔧 Recovering job {job.id}: {job.job_type}")
            
            # If this was a backup job, try to release any repository locks
            if job.job_type in ['backup', 'manual_backup', 'scheduled_backup']:
                repository = db.query(Repository).filter(Repository.id == job.repository_id).first()
                if repository:
                    await self._release_repository_lock(repository)
            
            # Mark the job as failed with recovery information
            job.status = 'failed'
            job.completed_at = datetime.now()
            job.error = f"Job recovered on startup - was running when application shut down (started: {job.started_at})"
            
            db.commit()
            logger.info(f"✅ Job {job.id} marked as failed and recovered")
            
        except Exception as e:
            logger.error(f"❌ Error recovering job {job.id}: {e}")
            db.rollback()
    
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
            current_time = datetime.now()
            
            for job_id, job_info in composite_job_manager.jobs.items():
                if job_info.status == 'running':
                    # Check if job has been running for more than reasonable time without progress
                    time_running = current_time - job_info.started_at
                    if time_running > timedelta(minutes=5):  # Adjust threshold as needed
                        stale_composite_jobs.append((job_id, job_info))
            
            if stale_composite_jobs:
                logger.info(f"🔍 Found {len(stale_composite_jobs)} stale composite jobs")
                
                db = next(get_db())
                try:
                    for job_id, job_info in stale_composite_jobs:
                        logger.info(f"🔧 Recovering composite job {job_id}")
                        
                        # Release repository lock if it was a backup job
                        if job_info.repository:
                            await self._release_repository_lock(job_info.repository)
                        
                        # Mark composite job as failed
                        job_info.status = 'failed'
                        job_info.completed_at = datetime.now()
                        
                        # Update database record
                        db_job = db.query(Job).filter(Job.id == job_info.db_job_id).first()
                        if db_job:
                            db_job.status = 'failed'
                            db_job.completed_at = datetime.now()
                            db_job.error = f"Composite job recovered on startup - was running when application shut down"
                    
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