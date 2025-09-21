import logging
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.responses import StreamingResponse
from pydantic import BaseModel
from borgitory.models.schemas import BackupRequest, PruneRequest, CheckRequest
from borgitory.models.enums import JobType
from borgitory.dependencies import JobServiceDep
from borgitory.dependencies import JobStreamServiceDep, JobRenderServiceDep
from borgitory.dependencies import TemplatesDep

logger = logging.getLogger(__name__)
router = APIRouter()


# Response Models
class JobResponse(BaseModel):
    """Generic job response model"""

    id: str
    status: str
    job_type: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    return_code: Optional[int] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Job status response model"""

    id: str
    status: str
    running: bool
    completed: bool
    failed: bool
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    job_type: Optional[str] = None
    current_task_index: Optional[int] = None
    tasks: Optional[int] = None


class JobOutputLine(BaseModel):
    """Job output line model"""

    text: str
    timestamp: Optional[str] = None
    stream: Optional[str] = None


class JobOutputResponse(BaseModel):
    """Job output response model"""

    lines: List[JobOutputLine]
    progress: Dict[str, str] = {}


class MessageResponse(BaseModel):
    """Generic message response model"""

    message: str


class JobManagerStatsResponse(BaseModel):
    """Job manager statistics response model"""

    total_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_processes: int
    running_job_ids: List[str]


class QueueStatsResponse(BaseModel):
    """Queue statistics response model"""

    max_concurrent_backups: int
    running_backups: int
    queued_backups: int
    available_slots: int
    queue_size: int


class MigrationResponse(BaseModel):
    """Database migration response model"""

    message: str
    success: Optional[bool] = None
    affected_rows: Optional[int] = None


@router.post("/backup", response_class=HTMLResponse)
async def create_backup(
    backup_request: BackupRequest,
    request: Request,
    job_svc: JobServiceDep,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Start a backup job using JobService"""

    try:
        result = await job_svc.create_backup_job(backup_request, JobType.MANUAL_BACKUP)
        job_id = result["job_id"]

        return templates.TemplateResponse(
            request,
            "partials/jobs/backup_success.html",
            {"job_id": job_id},
        )

    except ValueError as e:
        error_msg = f"Repository not found: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/jobs/backup_error.html",
            {"error_message": error_msg},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Failed to start backup: {e}")
        error_msg = f"Failed to start backup: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/jobs/backup_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.post("/prune")
async def create_prune_job(
    request: Request,
    prune_request: PruneRequest,
    job_svc: JobServiceDep,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Start an archive pruning job using JobService"""

    try:
        result = await job_svc.create_prune_job(prune_request)
        job_id = result["job_id"]

        return templates.TemplateResponse(
            request,
            "partials/prune/prune_success.html",
            {"job_id": job_id},
        )
    except ValueError as e:
        error_msg = str(e)
        return templates.TemplateResponse(
            request,
            "partials/prune/prune_error.html",
            {"error_message": error_msg},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Failed to start prune job: {e}")
        error_msg = f"Failed to start prune job: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/prune/prune_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.post("/check")
async def create_check_job(
    request: Request,
    check_request: CheckRequest,
    job_svc: JobServiceDep,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Start a repository check job and return job_id for tracking"""

    try:
        result = await job_svc.create_check_job(check_request)

        return templates.TemplateResponse(
            request,
            "partials/repository_check/check_success.html",
            {"job_id": result.get("job_id", "unknown")},
        )

    except ValueError as e:
        error_msg = str(e)
        return templates.TemplateResponse(
            request,
            "partials/repository_check/check_error.html",
            {"error_message": error_msg},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Failed to start check job: {e}")
        error_msg = f"Failed to start check job: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/repository_check/check_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.get("/stream")
async def stream_all_jobs(
    stream_svc: JobStreamServiceDep,
) -> StreamingResponse:
    """Stream real-time updates for all jobs via Server-Sent Events"""
    return await stream_svc.stream_all_jobs()


@router.get("/html", response_class=HTMLResponse)
def get_jobs_html(
    render_svc: JobRenderServiceDep,
    job_svc: JobServiceDep,
    expand: str = "",
) -> str:
    """Get job history as HTML"""
    return render_svc.render_jobs_html(job_svc.db, expand)


@router.get("/current/html", response_class=HTMLResponse)
def get_current_jobs_html(render_svc: JobRenderServiceDep) -> HTMLResponse:
    """Get current running jobs as HTML"""
    html_content = render_svc.render_current_jobs_html()
    return HTMLResponse(content=html_content)


@router.get("/current/stream")
async def stream_current_jobs_html(
    render_svc: JobRenderServiceDep,
) -> StreamingResponse:
    """Stream current running jobs as HTML via Server-Sent Events"""

    return StreamingResponse(
        render_svc.stream_current_jobs_html(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str, job_svc: JobServiceDep) -> JobStatusResponse:
    """Get current job status and progress"""
    try:
        output = await job_svc.get_job_status(job_id)
        if "error" in output:
            raise HTTPException(status_code=404, detail=str(output["error"]))

        # Create JobStatusResponse with proper type casting
        def safe_int(value: object) -> Optional[int]:
            """Safely convert value to int or None"""
            if value is None:
                return None
            if isinstance(value, (int, float, str)):
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return None
            return None

        return JobStatusResponse(
            id=str(output["id"]),
            status=str(output["status"]),
            running=bool(output["running"]),
            completed=bool(output["completed"]),
            failed=bool(output["failed"]),
            started_at=str(output["started_at"]) if output.get("started_at") else None,
            completed_at=str(output["completed_at"])
            if output.get("completed_at")
            else None,
            return_code=safe_int(output.get("return_code")),
            error=str(output["error"]) if output.get("error") else None,
            job_type=str(output["job_type"]) if output.get("job_type") else None,
            current_task_index=safe_int(output.get("current_task_index")),
            tasks=safe_int(output.get("tasks")),
        )
    except HTTPException:
        raise  # Re-raise HTTPExceptions without modification
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/stream")
async def stream_job_output(
    job_id: str,
    stream_svc: JobStreamServiceDep,
) -> StreamingResponse:
    """Stream real-time job output via Server-Sent Events"""
    return await stream_svc.stream_job_output(job_id)


@router.get("/{job_id}/toggle-details", response_class=HTMLResponse)
async def toggle_job_details(
    job_id: str,
    request: Request,
    render_svc: JobRenderServiceDep,
    templates: TemplatesDep,
    job_svc: JobServiceDep,
    expanded: str = "false",
) -> HTMLResponse:
    """Toggle job details visibility and return refreshed job item"""
    # Toggle the expand_details state - if currently false, expand it
    expand_details = expanded == "false"

    template_job = render_svc.get_job_for_template(job_id, job_svc.db, expand_details)
    if not template_job:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.debug(f"Job toggle - rendering job {job_id}")

    # Return the complete job item with new state
    return templates.TemplateResponse(
        request, "partials/jobs/job_item.html", template_job.__dict__
    )


@router.get("/{job_id}/details-static", response_class=HTMLResponse)
async def get_job_details_static(
    job_id: str,
    request: Request,
    render_svc: JobRenderServiceDep,
    templates: TemplatesDep,
    job_svc: JobServiceDep,
) -> HTMLResponse:
    """Get static job details (used when job completes)"""
    template_job = render_svc.get_job_for_template(job_id, job_svc.db)
    if not template_job:
        raise HTTPException(status_code=404, detail="Job not found")

    return templates.TemplateResponse(
        request, "partials/jobs/job_details_static.html", template_job.__dict__
    )


@router.get("/{job_id}/tasks/{task_order}/toggle-details", response_class=HTMLResponse)
async def toggle_task_details(
    job_id: str,
    task_order: int,
    request: Request,
    render_svc: JobRenderServiceDep,
    templates: TemplatesDep,
    job_svc: JobServiceDep,
    expanded: str = "false",
) -> HTMLResponse:
    """Toggle task details visibility and return updated task item"""
    template_job = render_svc.get_job_for_template(job_id, job_svc.db)
    if not template_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Find the specific task by order
    task = None
    for t in template_job.sorted_tasks:
        if t.task_order == task_order:
            task = t
            break

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Toggle task expansion state
    task_expanded = expanded == "false"  # If currently false, expand it

    # Create context for the task template
    context = {
        "job": template_job.job,  # Pass the job context object, not the full template data
        "task": task,
        "task_expanded": task_expanded,
    }

    # Choose appropriate template based on job status
    if str(template_job.job.status) == "running":
        template_name = "partials/jobs/task_item_streaming.html"
    else:
        template_name = "partials/jobs/task_item_static.html"

    return templates.TemplateResponse(request, template_name, context)


@router.post("/{job_id}/copy-output", response_model=MessageResponse)
async def copy_job_output() -> MessageResponse:
    """Copy job output to clipboard (returns success message)"""
    return MessageResponse(message="Output copied to clipboard")


@router.get("/{job_id}/tasks/{task_order}/stream")
async def stream_task_output(
    job_id: str,
    task_order: int,
    stream_svc: JobStreamServiceDep,
) -> StreamingResponse:
    """Stream real-time output for a specific task via Server-Sent Events"""
    return await stream_svc.stream_task_output(job_id, task_order)


@router.post("/{job_id}/tasks/{task_order}/copy-output", response_model=MessageResponse)
async def copy_task_output() -> MessageResponse:
    """Copy task output to clipboard (returns success message)"""
    return MessageResponse(message="Task output copied to clipboard")
