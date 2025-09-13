"""
Job execution service using FastAPI BackgroundTasks following best practices.

This service demonstrates proper background job management with clean architecture.
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional, List
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select

from app.models.repository import Repository, Job
from app.models.schemas import BackupRequest, JobResponse, BackupResult
from app.models.enums import JobType, JobStatus
from app.services.interfaces import (
    CommandExecutor,
    SecurityValidator,
    RepositoryValidationError,
    CommandResult
)

logger = logging.getLogger(__name__)


class JobExecutionService:
    """
    Job execution service using clean architecture and FastAPI BackgroundTasks.
    
    Following FastAPI BackgroundTasks best practices:
    - Lightweight background operations
    - Database state tracking
    - Proper error handling and logging
    """
    
    def __init__(
        self,
        command_executor: CommandExecutor,
        security_validator: SecurityValidator,
        session_factory: sessionmaker
    ):
        self.command_executor = command_executor
        self.security_validator = security_validator
        self.session_factory = session_factory
    
    async def execute_backup_task(
        self,
        job_id: int,
        repository: Repository,
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False
    ) -> None:
        """
        Execute backup task in background following FastAPI BackgroundTasks pattern.
        
        This function is designed to be called by FastAPI BackgroundTasks.
        It updates job status in database as it progresses.
        """
        # Use injected session factory for background task (proper DI)
        with self.session_factory() as db:
            try:
                # Get job from database
                job = db.get(Job, job_id)
                if not job:
                    logger.error(f"Job {job_id} not found for execution")
                    return
                
                # Update job status to running using enum
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(UTC)
                job.current_step = "Starting backup"
                job.progress_percentage = 0
                db.commit()
                
                logger.info(f"Starting backup job {job_id} for repository {repository.name}")
                
                # Build backup command
                archive_name = f"backup-{datetime.now(UTC).strftime('%Y-%m-%d_%H-%M-%S')}"
                command = [
                    "borg", "create",
                    "--compression", compression,
                    "--stats", "--progress", "--json",
                    f"{repository.path}::{archive_name}",
                    source_path
                ]
                
                if dry_run:
                    command.insert(2, "--dry-run")
                
                env = {
                    "BORG_PASSPHRASE": repository.get_passphrase(),
                    "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"
                }
                
                # Update progress
                job.current_step = "Executing backup command"
                job.progress_percentage = 10
                db.commit()
                
                # Execute backup command
                result = await self.command_executor.run_command(
                    command=command,
                    env=env,
                    timeout=3600  # 1 hour timeout for backups
                )
                
                # Update job with results
                job.return_code = result.return_code
                job.completed_at = datetime.now(UTC)
                job.progress_percentage = 100
                
                if result.success:
                    job.status = JobStatus.COMPLETED
                    job.current_step = "Backup completed successfully"
                    job.output_log = result.stdout.decode('utf-8', errors='replace')
                    logger.info(f"Backup job {job_id} completed successfully")
                else:
                    job.status = JobStatus.FAILED
                    job.current_step = "Backup failed"
                    job.error_message = result.stderr.decode('utf-8', errors='replace')
                    job.output_log = result.stdout.decode('utf-8', errors='replace')
                    logger.error(f"Backup job {job_id} failed with return code {result.return_code}")
                
                db.commit()
                
            except Exception as e:
                # Handle unexpected errors
                logger.exception(f"Unexpected error in backup job {job_id}: {e}")
                
                try:
                    job = db.get(Job, job_id)
                    if job:
                        job.status = JobStatus.FAILED
                        job.completed_at = datetime.now(UTC)
                        job.current_step = "Error occurred"
                        job.error_message = str(e)
                        job.progress_percentage = 0
                        db.commit()
                except Exception as db_error:
                    logger.exception(f"Failed to update job {job_id} error status: {db_error}")


class JobManagementService:
    """
    Job management service using clean architecture patterns.
    
    Handles job creation, status tracking, and coordination with BackgroundTasks.
    """
    
    def __init__(self, job_executor: JobExecutionService):
        self.job_executor = job_executor
    
    async def create_backup_job(
        self,
        backup_request: BackupRequest,
        db: Session
    ) -> BackupResult:
        """
        Create backup job following FastAPI BackgroundTasks best practices.
        
        Creates job record and returns immediately, execution happens in background.
        """
        # Validate repository exists
        repository = db.get(Repository, backup_request.repository_id)
        if not repository:
            raise RepositoryValidationError(f"Repository {backup_request.repository_id} not found")
        
        # Create job record using enums
        job = Job(
            repository_id=backup_request.repository_id,
            job_type=JobType.BACKUP,
            status=JobStatus.PENDING,
            source_path=backup_request.source_path,
            compression=backup_request.compression,
            current_step="Job created, waiting to start"
        )
        
        db.add(job)
        db.flush()  # Get job ID without committing
        db.refresh(job)
        
        logger.info(f"Created backup job {job.id} for repository {repository.name}")
        
        return BackupResult(
            job_id=job.id,
            status="pending",
            message=f"Backup job created for repository '{repository.name}'. Job will start in background."
        )
    
    def get_job_status(self, job_id: int, db: Session) -> Optional[JobResponse]:
        """Get job status and details."""
        job = db.get(Job, job_id)
        if not job:
            return None
        
        return JobResponse.model_validate(job)
    
    def list_jobs(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status_filter: Optional[str] = None
    ) -> List[JobResponse]:
        """List jobs with filtering and pagination."""
        stmt = select(Job).order_by(Job.created_at.desc())
        
        if status_filter:
            stmt = stmt.where(Job.status == status_filter)
        
        stmt = stmt.offset(skip).limit(limit)
        jobs = list(db.scalars(stmt))
        
        return [JobResponse.model_validate(job) for job in jobs]