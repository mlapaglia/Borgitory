"""
Multi-task job workflow service following clean architecture.

This service orchestrates complex jobs with multiple sequential tasks.
"""

import logging
from datetime import datetime, UTC
from typing import List, Optional
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select

from app.models.repository import Job, Task, Repository, NotificationConfig
from app.models.enums import JobType, JobStatus, TaskType, TaskStatus
from app.services.interfaces import (
    TaskExecutionService,
    NotificationService,
    CommandExecutor,
    SecurityValidator
)

logger = logging.getLogger(__name__)


class TaskDefinition:
    """Definition for a task in a workflow."""
    def __init__(
        self,
        task_type: TaskType,
        task_order: int,
        depends_on_success: bool = True,
        notification_config_id: Optional[int] = None
    ):
        self.task_type = task_type
        self.task_order = task_order
        self.depends_on_success = depends_on_success
        self.notification_config_id = notification_config_id


class TaskExecutionServiceImpl:
    """Task execution service for individual task types."""
    
    def __init__(
        self,
        command_executor: CommandExecutor,
        notification_service: NotificationService,
        job_executor: 'JobExecutionService',
        session_factory: sessionmaker
    ):
        self.command_executor = command_executor
        self.notification_service = notification_service
        self.job_executor = job_executor
        self.session_factory = session_factory
    
    async def execute_backup_task(
        self,
        job_id: int,
        repository: Repository,
        source_path: str,
        compression,
        dry_run: bool = False
    ) -> bool:
        """Execute backup task (reusing existing logic)."""
        try:
            await self.job_executor.execute_backup_task(
                job_id, repository, source_path, compression, dry_run
            )
            
            # Check if backup succeeded
            with self.session_factory() as db:
                job = db.get(Job, job_id)
                return job and job.status == JobStatus.COMPLETED
                
        except Exception as e:
            logger.exception(f"Backup task execution failed: {e}")
            return False
    
    async def execute_notification_task(
        self,
        job_id: int,
        task_id: int,
        notification_config: NotificationConfig,
        backup_result: bool
    ) -> bool:
        """Execute notification task."""
        try:
            # Update task status
            with self.session_factory() as db:
                task = db.get(Task, task_id)
                if not task:
                    logger.error(f"Task {task_id} not found")
                    return False
                
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(UTC)
                db.commit()
                
                # Get repository info for notification
                job = db.get(Job, job_id)
                if not job or not job.repository:
                    logger.error(f"Job {job_id} or repository not found")
                    return False
                
                repository_name = job.repository.name
                
                # Send notification
                success = await self.notification_service.send_backup_notification(
                    notification_config=notification_config,
                    repository_name=repository_name,
                    backup_success=backup_result,
                    job_details=f"Job #{job_id}"
                )
                
                # Update task status
                task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                task.completed_at = datetime.now(UTC)
                task.return_code = 0 if success else 1
                
                if not success:
                    task.error_message = "Failed to send notification"
                
                db.commit()
                
                logger.info(f"Notification task {task_id} {'completed' if success else 'failed'}")
                return success
                
        except Exception as e:
            logger.exception(f"Notification task execution failed: {e}")
            
            # Mark task as failed
            try:
                with self.session_factory() as db:
                    task = db.get(Task, task_id)
                    if task:
                        task.status = TaskStatus.FAILED
                        task.completed_at = datetime.now(UTC)
                        task.error_message = str(e)
                        task.return_code = 1
                        db.commit()
            except Exception as db_error:
                logger.exception(f"Failed to update task status: {db_error}")
            
            return False


class JobWorkflowServiceImpl:
    """
    Multi-task job workflow service implementation.
    
    Orchestrates sequential task execution with conditional logic.
    """
    
    def __init__(
        self,
        task_executor: TaskExecutionService,
        session_factory: sessionmaker
    ):
        self.task_executor = task_executor
        self.session_factory = session_factory
    
    async def create_workflow_job(
        self,
        repository_id: int,
        source_path: str,
        compression,
        tasks: List[TaskDefinition],
        db: Session,
        dry_run: bool = False
    ) -> int:
        """Create multi-task workflow job."""
        # Create main job
        job = Job(
            repository_id=repository_id,
            job_type=JobType.BACKUP,  # Main job type
            status=JobStatus.PENDING,
            source_path=source_path,
            compression=compression,
            current_step="Workflow created, preparing tasks"
        )
        
        db.add(job)
        db.flush()
        db.refresh(job)
        
        # Create tasks
        for task_def in tasks:
            task = Task(
                job_id=job.id,
                task_type=task_def.task_type,
                task_order=task_def.task_order,
                status=TaskStatus.PENDING,
                depends_on_success=task_def.depends_on_success,
                notification_config_id=task_def.notification_config_id
            )
            db.add(task)
        
        db.commit()
        
        logger.info(f"Created workflow job {job.id} with {len(tasks)} tasks")
        return job.id
    
    async def execute_workflow(
        self,
        job_id: int
    ) -> None:
        """
        Execute all tasks in workflow sequentially.
        
        Designed for FastAPI BackgroundTasks execution.
        """
        with self.session_factory() as db:
            try:
                # Get job and tasks
                job = db.get(Job, job_id)
                if not job:
                    logger.error(f"Workflow job {job_id} not found")
                    return
                
                # Update job status
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(UTC)
                job.current_step = "Executing workflow tasks"
                db.commit()
                
                # Get tasks in order
                stmt = select(Task).where(Task.job_id == job_id).order_by(Task.task_order)
                tasks = list(db.scalars(stmt))
                
                logger.info(f"Starting workflow execution for job {job_id} with {len(tasks)} tasks")
                
                previous_task_success = True
                
                for task in tasks:
                    # Check if task should run
                    if task.depends_on_success and not previous_task_success:
                        logger.info(f"Skipping task {task.id} due to previous task failure")
                        task.status = TaskStatus.SKIPPED
                        task.started_at = datetime.now(UTC)
                        task.completed_at = datetime.now(UTC)
                        db.commit()
                        continue
                    
                    # Execute task based on type
                    task_success = False
                    
                    if task.task_type == TaskType.BACKUP:
                        task_success = await self.task_executor.execute_backup_task(
                            job_id=job_id,
                            repository=job.repository,
                            source_path=job.source_path,
                            compression=job.compression,
                            dry_run=True  # For sandbox safety
                        )
                    
                    elif task.task_type == TaskType.NOTIFICATION:
                        # Get notification config
                        notification_config = db.get(NotificationConfig, task.notification_config_id)
                        if notification_config:
                            task_success = await self.task_executor.execute_notification_task(
                                job_id=job_id,
                                task_id=task.id,
                                notification_config=notification_config,
                                backup_result=previous_task_success
                            )
                        else:
                            logger.error(f"Notification config {task.notification_config_id} not found")
                    
                    previous_task_success = task_success
                
                # Update overall job status
                job = db.get(Job, job_id)  # Refresh job
                if job:
                    all_tasks_stmt = select(Task).where(Task.job_id == job_id)
                    all_tasks = list(db.scalars(all_tasks_stmt))
                    
                    # Determine overall job status
                    if all(t.status in [TaskStatus.COMPLETED, TaskStatus.SKIPPED] for t in all_tasks):
                        job.status = JobStatus.COMPLETED
                        job.current_step = "All tasks completed successfully"
                    elif any(t.status == TaskStatus.FAILED for t in all_tasks):
                        job.status = JobStatus.FAILED
                        job.current_step = "Workflow failed"
                    
                    job.completed_at = datetime.now(UTC)
                    job.progress_percentage = 100
                    db.commit()
                
                logger.info(f"Workflow execution completed for job {job_id}")
                
            except Exception as e:
                logger.exception(f"Workflow execution failed for job {job_id}: {e}")
                
                # Mark job as failed
                try:
                    job = db.get(Job, job_id)
                    if job:
                        job.status = JobStatus.FAILED
                        job.completed_at = datetime.now(UTC)
                        job.current_step = "Workflow execution error"
                        job.error_message = str(e)
                        db.commit()
                except Exception as db_error:
                    logger.exception(f"Failed to update job error status: {db_error}")