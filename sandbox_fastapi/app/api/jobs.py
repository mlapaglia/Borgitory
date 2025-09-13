"""
Job API endpoints following FastAPI BackgroundTasks best practices.

This demonstrates proper background job management with clean architecture.
"""

import logging
from datetime import datetime, UTC
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse

from app.models.repository import Repository, Job, NotificationConfig
from app.models.schemas import BackupRequest, JobResponse, BackupResult, WorkflowJobRequest
from app.dependencies import JobManagementServiceDep, JobExecutionServiceDep, DatabaseDep, JobWorkflowServiceDep, TemplatesDep
from app.services.workflow_service import TaskDefinition
from app.models.enums import TaskType
from app.services.interfaces import RepositoryValidationError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/backup", response_class=HTMLResponse)
async def start_backup_workflow(
    request: Request,
    templates: TemplatesDep,
    background_tasks: BackgroundTasks,
    workflow_service: JobWorkflowServiceDep,
    db: DatabaseDep,
    repository_id: int = Form(...),
    source_path: str = Form(...),
    compression: str = Form("zstd"),
    dry_run: bool = Form(False),
    notification_config_id: Optional[int] = Form(None)
):
    """
    Start backup workflow (unified approach - all jobs are workflows).
    
    Creates 1-task workflow (backup only) or 2-task workflow (backup + notification).
    HTMX PRINCIPLE: Returns HTML status fragment, never JSON.
    """
    try:
        # Validate inputs
        repository = db.get(Repository, repository_id)
        if not repository:
            return templates.TemplateResponse(
                request,
                "partials/jobs/backup_error.html",
                {"error_message": "Repository not found"}
            )
        
        # Validate compression enum
        try:
            from app.models.enums import CompressionType
            compression_enum = CompressionType(compression)
        except ValueError:
            return templates.TemplateResponse(
                request,
                "partials/jobs/backup_error.html",
                {"error_message": f"Invalid compression type: {compression}"}
            )
        
        # Build task list (always workflow-based)
        from app.services.workflow_service import TaskDefinition
        tasks = [
            TaskDefinition(TaskType.BACKUP, 1, depends_on_success=False)
        ]
        
        # Add notification task if config provided
        notification_config = None
        if notification_config_id:
            notification_config = db.get(NotificationConfig, notification_config_id)
            if notification_config and notification_config.enabled:
                tasks.append(
                    TaskDefinition(
                        TaskType.NOTIFICATION, 
                        2, 
                        depends_on_success=False,  # Send notification even if backup fails
                        notification_config_id=notification_config_id
                    )
                )
        
        # Create workflow job (unified approach)
        job_id = await workflow_service.create_workflow_job(
            repository_id=repository_id,
            source_path=source_path,
            compression=compression_enum,
            tasks=tasks,
            db=db,
            dry_run=dry_run
        )
        
        # Start workflow execution in background
        background_tasks.add_task(workflow_service.execute_workflow, job_id)
        
        logger.info(f"Started workflow job {job_id} with {len(tasks)} tasks")
        
        return templates.TemplateResponse(
            request,
            "partials/jobs/backup_started.html",
            {
                "job_id": job_id,
                "repository_name": repository.name,
                "source_path": source_path,
                "task_count": len(tasks),
                "has_notification": notification_config is not None,
                "notification_name": notification_config.name if notification_config else None
            }
        )
        
    except Exception as e:
        logger.error(f"Workflow job creation error: {e}")
        return templates.TemplateResponse(
            request,
            "partials/jobs/backup_error.html",
            {"error_message": str(e)}
        )


@router.get("/", response_class=HTMLResponse)
def list_jobs_html(
    request: Request,
    templates: TemplatesDep,
    job_management_service: JobManagementServiceDep,
    db: DatabaseDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None)
):
    """
    List jobs as HTML for HTMX.
    
    HTMX PRINCIPLE: Returns HTML template, never JSON.
    """
    try:
        jobs = job_management_service.list_jobs(db, skip, limit, status)
        return templates.TemplateResponse(
            request,
            "partials/jobs/job_list.html",
            {"jobs": jobs}
        )
    except Exception as e:
        logger.error(f"Error loading jobs: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Failed to load jobs"}
        )


@router.get("/{job_id}/output", response_class=HTMLResponse)
def get_job_output(
    request: Request,
    templates: TemplatesDep,
    job_id: int,
    job_management_service: JobManagementServiceDep,
    db: DatabaseDep
):
    """
    Get job output as HTML fragment for HTMX.
    
    HTMX PRINCIPLE: Returns HTML template, never JSON.
    """
    job = job_management_service.get_job_status(job_id, db)
    if not job:
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Job not found"}
        )
    
    if job.status not in ["completed", "failed"]:
        return templates.TemplateResponse(
            request,
            "partials/jobs/job_not_ready.html",
            {"job_id": job_id, "status": job.status}
        )
    
    return templates.TemplateResponse(
        request,
        "partials/jobs/job_output.html",
        {
            "job_id": job_id,
            "status": job.status,
            "output_log": job.output_log or "",
            "error_message": job.error_message or "",
            "return_code": job.return_code
        }
    )


@router.delete("/{job_id}", response_class=HTMLResponse)
def cancel_job(
    request: Request,
    templates: TemplatesDep,
    job_id: int,
    job_management_service: JobManagementServiceDep,
    db: DatabaseDep
):
    """
    Cancel job returning HTML fragment for HTMX.
    
    HTMX PRINCIPLE: Returns HTML confirmation, never JSON.
    """
    job = job_management_service.get_job_status(job_id, db)
    if not job:
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Job not found"}
        )
    
    if job.status not in ["pending", "running"]:
        return templates.TemplateResponse(
            request,
            "partials/jobs/cancel_error.html",
            {"error_message": "Job cannot be cancelled", "job_id": job_id, "status": job.status}
        )
    
    # Cancel the job using the injected database session
    job_record = db.get(Job, job_id)
    if job_record:
        from app.models.enums import JobStatus
        job_record.status = JobStatus.CANCELLED
        job_record.completed_at = datetime.now(UTC)
        job_record.error_message = "Job cancelled by user"
        job_record.current_step = "Cancelled"
        db.commit()
    
    return templates.TemplateResponse(
        request,
        "partials/jobs/cancel_success.html",
        {"job_id": job_id, "message": f"Job {job_id} cancelled successfully"}
    )


