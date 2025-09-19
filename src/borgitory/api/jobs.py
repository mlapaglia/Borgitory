import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.responses import StreamingResponse
from borgitory.models.schemas import BackupRequest, PruneRequest, CheckRequest
from borgitory.models.enums import JobType
from borgitory.dependencies import JobServiceDep
from borgitory.dependencies import JobStreamServiceDep, JobRenderServiceDep
from borgitory.services.jobs.job_manager import JobManager
from borgitory.protocols.job_protocols import JobManagerProtocol
from borgitory.dependencies import TemplatesDep

logger = logging.getLogger(__name__)
router = APIRouter()


def get_job_manager_dependency() -> JobManagerProtocol:
    """Dependency to get modular job manager instance."""
    from borgitory.dependencies import get_job_manager_dependency as get_jm_dep

    return get_jm_dep()


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


@router.get("/")
def list_jobs(
    job_svc: JobServiceDep,
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List database job records (legacy jobs) and active JobManager jobs"""
    return job_svc.list_jobs(skip, limit, type)


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


@router.get("/{job_id}")
def get_job(
    job_id: str,
    job_svc: JobServiceDep,
) -> Dict[str, Any]:
    """Get job details - supports both database IDs and JobManager IDs"""
    job = job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/status")
async def get_job_status(job_id: str, job_svc: JobServiceDep) -> Dict[str, Any]:
    """Get current job status and progress"""
    try:
        output = await job_svc.get_job_status(job_id)
        if "error" in output:
            raise HTTPException(status_code=404, detail=output["error"])
        return output
    except HTTPException:
        raise  # Re-raise HTTPExceptions without modification
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/output")
async def get_job_output(
    job_id: str,
    job_svc: JobServiceDep,
    last_n_lines: int = 100,
) -> Dict[str, Any]:
    """Get job output lines"""
    try:
        output = await job_svc.get_job_output(job_id, last_n_lines)
        if "error" in output:
            raise HTTPException(status_code=404, detail=output["error"])
        return output
    except HTTPException:
        raise  # Re-raise HTTPExceptions without modification
    except Exception as e:
        logger.error(f"Error getting job output: {e}")
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
    job = render_svc.get_job_for_render(job_id, job_svc.db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Toggle the expand_details state
    job["expand_details"] = expanded == "false"  # If currently false, expand it

    logger.debug(f"Job toggle - rendering job {job_id}")

    # Return the complete job item with new state
    return templates.TemplateResponse(request, "partials/jobs/job_item.html", job)


@router.get("/{job_id}/details-static", response_class=HTMLResponse)
async def get_job_details_static(
    job_id: str,
    request: Request,
    render_svc: JobRenderServiceDep,
    templates: TemplatesDep,
    job_svc: JobServiceDep,
) -> HTMLResponse:
    """Get static job details (used when job completes)"""
    job = render_svc.get_job_for_render(job_id, job_svc.db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return templates.TemplateResponse(
        request, "partials/jobs/job_details_static.html", job
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
    job = render_svc.get_job_for_render(job_id, job_svc.db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Find the specific task
    task = None
    if job.get("sorted_tasks"):
        for t in job["sorted_tasks"]:
            if t.task_order == task_order:
                task = t
                break

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Toggle the task expanded state
    task_expanded = expanded == "false"  # If currently false, expand it

    # Create context for the task template - use the UUID-based job context from render service
    context = {
        "job": job[
            "job"
        ],  # This is already the UUID-based job context from _format_manager_job_for_render
        "task": task,
        "task_expanded": task_expanded,
    }

    # Choose appropriate template based on job status
    if job["job"].status == "running":
        template_name = "partials/jobs/task_item_streaming.html"
    else:
        template_name = "partials/jobs/task_item_static.html"

    return templates.TemplateResponse(request, template_name, context)


@router.post("/{job_id}/copy-output")
async def copy_job_output() -> Dict[str, Any]:
    """Copy job output to clipboard (returns success message)"""
    return {"message": "Output copied to clipboard"}


@router.get("/{job_id}/tasks/{task_order}/stream")
async def stream_task_output(
    job_id: str,
    task_order: int,
    stream_svc: JobStreamServiceDep,
) -> StreamingResponse:
    """Stream real-time output for a specific task via Server-Sent Events"""
    return await stream_svc.stream_task_output(job_id, task_order)


@router.post("/{job_id}/tasks/{task_order}/copy-output")
async def copy_task_output() -> Dict[str, Any]:
    """Copy task output to clipboard (returns success message)"""
    return {"message": "Task output copied to clipboard"}


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    job_svc: JobServiceDep,
) -> Dict[str, Any]:
    """Cancel a running job"""
    success = await job_svc.cancel_job(job_id)
    if success:
        return {"message": "Job cancelled successfully"}
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/manager/stats")
def get_job_manager_stats(
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> Dict[str, Any]:
    """Get JobManager statistics"""
    jobs = job_manager.jobs
    running_jobs = [job for job in jobs.values() if job.status == "running"]
    completed_jobs = [job for job in jobs.values() if job.status == "completed"]
    failed_jobs = [job for job in jobs.values() if job.status == "failed"]

    return {
        "total_jobs": len(jobs),
        "running_jobs": len(running_jobs),
        "completed_jobs": len(completed_jobs),
        "failed_jobs": len(failed_jobs),
        "active_processes": len(job_manager._processes),
        "running_job_ids": [job.id for job in running_jobs],
    }


@router.post("/manager/prune")
def cleanup_completed_jobs(
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> Dict[str, Any]:
    """Clean up completed jobs from JobManager memory"""
    cleaned = 0
    jobs_to_remove = []

    for job_id, job in job_manager.jobs.items():
        if job.status in ["completed", "failed"]:
            jobs_to_remove.append(job_id)

    for job_id in jobs_to_remove:
        job_manager.cleanup_job(job_id)
        cleaned += 1

    return {"message": f"Cleaned up {cleaned} completed jobs"}


@router.get("/queue/stats")
def get_queue_stats(
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> Dict[str, Any]:
    """Get backup queue statistics"""
    return job_manager.get_queue_stats()


@router.post("/migrate")
def run_database_migration(job_svc: JobServiceDep) -> Dict[str, Any]:
    """Manually trigger database migration for jobs table"""
    try:
        return job_svc.run_database_migration()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
