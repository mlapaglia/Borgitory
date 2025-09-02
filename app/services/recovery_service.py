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
        Find backup jobs that were running when the app was shut down and clean them up.
        This should be called on application startup.
        
        All backup operations (manual and scheduled) use the composite job system.
        Legacy jobs are only used for utility operations (scan, list archives, etc.) 
        which don't need recovery - they can simply be re-run if needed.
        """
        logger.info("🔧 Starting recovery: checking for interrupted jobs...")
        
        # Only need to check database Job records - in-memory composite jobs 
        # are always empty on startup since they don't persist across restarts
        await self.recover_database_job_records()
        
        logger.info("✅ Recovery complete - all interrupted backup jobs cancelled and locks released")
    
    async def recover_database_job_records(self):
        """
        Find database Job records that are marked as 'running' and mark them as failed.
        This handles the case where the app restarted and composite jobs are cleared from memory,
        but database records still show 'running' status.
        """
        try:
            print("🔥 RECOVERY: Checking database for interrupted job records...")
            logger.info("🔧 Checking database for interrupted job records...")
            
            db = next(get_db())
            try:
                from app.models.database import Job, JobTask
                
                # Find all jobs in database marked as running
                running_jobs = db.query(Job).filter(Job.status == 'running').all()
                print(f"🔥 RECOVERY: Found {len(running_jobs)} running jobs in database")
                
                if not running_jobs:
                    print("🔥 RECOVERY: No interrupted database job records found")
                    logger.info("✅ No interrupted database job records found")
                    return
                
                print(f"🔥 RECOVERY: Processing {len(running_jobs)} interrupted database job records")
                logger.info(f"🔍 Found {len(running_jobs)} interrupted database job records")
                
                for job in running_jobs:
                    print(f"🔥 RECOVERY: Processing job {job.id} ({job.job_type}) - repository_id: {job.repository_id}")
                    logger.info(f"🔧 Cancelling database job record {job.id} ({job.job_type}) - was running since {job.started_at}")
                    
                    # Mark job as failed
                    job.status = 'failed'
                    job.completed_at = datetime.now()
                    job.error = f"Error: Job cancelled on startup - was running when application shut down (started: {job.started_at})"
                    
                    # Mark all running tasks as failed
                    running_tasks = db.query(JobTask).filter(
                        JobTask.job_id == job.id,
                        JobTask.status.in_(['pending', 'running', 'in_progress'])
                    ).all()
                    
                    for task in running_tasks:
                        task.status = 'failed'
                        task.completed_at = datetime.now()
                        task.error = "Task cancelled on startup - job was interrupted by application shutdown"
                        logger.info(f"  ✅ Task '{task.task_name}' marked as failed")
                    
                    # Release repository lock if this was a backup job (including composite jobs)
                    if job.job_type in ['manual_backup', 'scheduled_backup', 'backup', 'composite'] and job.repository_id:
                        print(f"🔥 RECOVERY: Looking up repository {job.repository_id} for job {job.id}")
                        repository = db.query(Repository).filter(Repository.id == job.repository_id).first()
                        if repository:
                            print(f"🔥 RECOVERY: Found repository {repository.name}, releasing lock...")
                            logger.info(f"🔓 Releasing repository lock for: {repository.name}")
                            await self._release_repository_lock(repository)
                        else:
                            print(f"🔥 RECOVERY: Repository {job.repository_id} not found in database!")
                    else:
                        print(f"🔥 RECOVERY: Job {job.id} is not a backup job or has no repository_id")
                
                db.commit()
                logger.info("✅ All interrupted database job records cancelled")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Error recovering database job records: {e}")
    
    
    async def _release_repository_lock(self, repository: Repository):
        """Use borg break-lock to release any stale locks on a repository"""
        try:
            print(f"🔥 RECOVERY: Attempting to release lock on repository: {repository.name}")
            print(f"🔥 RECOVERY: Repository path: {repository.path}")
            logger.info(f"🔓 Attempting to release lock on repository: {repository.name}")
            
            # Build borg break-lock command
            command, env = build_secure_borg_command(
                base_command="borg break-lock",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=[]
            )
            
            print(f"🔥 RECOVERY: Break-lock command: {' '.join(command)}")
            
            # Execute the break-lock command with a timeout
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                
                stdout_text = stdout.decode() if stdout else "No stdout"
                stderr_text = stderr.decode() if stderr else "No stderr"
                
                print(f"🔥 RECOVERY: Break-lock return code: {process.returncode}")
                print(f"🔥 RECOVERY: Break-lock stdout: {stdout_text}")
                print(f"🔥 RECOVERY: Break-lock stderr: {stderr_text}")
                
                if process.returncode == 0:
                    print(f"🔥 RECOVERY: Successfully released lock on repository: {repository.name}")
                    logger.info(f"✅ Successfully released lock on repository: {repository.name}")
                else:
                    # Log the error but don't fail - lock might not exist
                    print(f"🔥 RECOVERY: Break-lock returned {process.returncode} for {repository.name}: {stderr_text}")
                    logger.warning(f"⚠️  Break-lock returned {process.returncode} for {repository.name}: {stderr_text}")
                    
            except asyncio.TimeoutError:
                print(f"🔥 RECOVERY: Break-lock timed out for repository: {repository.name}")
                logger.warning(f"⚠️  Break-lock timed out for repository: {repository.name}")
                process.kill()
                
        except Exception as e:
            print(f"🔥 RECOVERY: Error releasing lock for repository {repository.name}: {e}")
            logger.error(f"❌ Error releasing lock for repository {repository.name}: {e}")
    


# Global instance
recovery_service = RecoveryService()