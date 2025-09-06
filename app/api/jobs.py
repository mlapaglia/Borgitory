import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import get_db, Repository
from app.models.schemas import BackupRequest, PruneRequest, CheckRequest
from app.services.job_service import job_service, JobService
from app.services.job_render_service import job_render_service, JobRenderService
from app.services.job_stream_service import job_stream_service, JobStreamService
from app.services.job_manager import get_job_manager, BorgJobManager

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_job_manager_dependency() -> BorgJobManager:
    """Dependency to get job manager instance."""
    return get_job_manager()


@router.post("/backup", response_class=HTMLResponse)
async def create_backup(
    backup_request: BackupRequest,
    request: Request,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Start a backup job and return HTML status"""
    try:
        result = await job_svc.create_backup_job(backup_request, db)
        job_id = result["job_id"]

        # Return HTML showing the backup started
        return f"""
            <div id="backup-job-{job_id}" class="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div class="flex items-center">
                    <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                    <span class="text-blue-700 text-sm">Backup job #{job_id} started...</span>
                </div>
            </div>
        """
    except ValueError as e:
        # Return error HTML
        return f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-3">
                <span class="text-red-700 text-sm">Repository not found: {str(e)}</span>
            </div>
        """
    except Exception as e:
        logger.error(f"Failed to start backup: {e}")
        # Return error HTML
        return f"""
            <div class="bg-red-50 border border-red-200 rounded-lg p-3">
                <span class="text-red-700 text-sm">Failed to start backup: {str(e)}</span>
            </div>
        """


@router.post("/prune")
async def create_prune_job(
    request: Request,
    prune_request: PruneRequest,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Start an archive pruning job and return job_id for tracking"""
    is_htmx_request = "hx-request" in request.headers

    try:
        result = await job_svc.create_prune_job(prune_request, db)

        if is_htmx_request:
            repositories = db.query(Repository).all()
            return templates.TemplateResponse(
                request,
                "partials/cleanup/config_form_success.html",
                {"repositories": repositories},
            )
        else:
            return result
    except ValueError as e:
        error_msg = str(e)
        if is_htmx_request:
            repositories = db.query(Repository).all()
            return templates.TemplateResponse(
                request,
                "partials/cleanup/config_form_error.html",
                {
                    "error_message": error_msg,
                    "repositories": repositories,
                },
                status_code=200,
            )
        raise HTTPException(status_code=404, detail=error_msg)
    except Exception as e:
        logger.error(f"Failed to start prune job: {e}")
        error_msg = f"Failed to start prune job: {str(e)}"
        if is_htmx_request:
            repositories = db.query(Repository).all()
            return templates.TemplateResponse(
                request,
                "partials/cleanup/config_form_error.html",
                {
                    "error_message": error_msg,
                    "repositories": repositories,
                },
                status_code=200,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/check")
async def create_check_job(
    check_request: CheckRequest,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Start a repository check job and return job_id for tracking"""
    try:
        result = await job_svc.create_check_job(check_request, db)
        return result
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        elif "disabled" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start check job: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start check job: {str(e)}"
        )


@router.get("/stream")
async def stream_all_jobs(
    stream_svc: JobStreamService = Depends(lambda: job_stream_service),
):
    """Stream real-time updates for all jobs via Server-Sent Events"""
    return await stream_svc.stream_all_jobs()


@router.get("/")
def list_jobs(
    skip: int = 0,
    limit: int = 100,
    type: str = None,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """List database job records (legacy jobs) and active JobManager jobs"""
    return job_svc.list_jobs(skip, limit, type, db)


@router.get("/html", response_class=HTMLResponse)
def get_jobs_html(
    request: Request,
    expand: str = None,
    db: Session = Depends(get_db),
    render_svc: JobRenderService = Depends(lambda: job_render_service),
):
    """Get job history as HTML"""
    return render_svc.render_jobs_html(db, expand)


@router.get("/current/html", response_class=HTMLResponse)
def get_current_jobs_html(
    request: Request, render_svc: JobRenderService = Depends(lambda: job_render_service)
):
    """Get current running jobs as HTML"""
    html_content = render_svc.render_current_jobs_html()
    return HTMLResponse(content=html_content)


@router.get("/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Get job details - supports both database IDs and JobManager IDs"""
    job = job_svc.get_job(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: str, job_svc: JobService = Depends(lambda: job_service)
):
    """Get current job status and progress"""
    try:
        output = await job_svc.get_job_status(job_id)
        if "error" in output:
            raise HTTPException(status_code=404, detail=output["error"])
        return output
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/output")
async def get_job_output(
    job_id: str,
    last_n_lines: int = 100,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Get job output lines"""
    try:
        output = await job_svc.get_job_output(job_id, last_n_lines)
        if "error" in output:
            raise HTTPException(status_code=404, detail=output["error"])
        return output
    except Exception as e:
        logger.error(f"Error getting job output: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/stream")
async def stream_job_output(
    job_id: str,
    db: Session = Depends(get_db),
    stream_svc: JobStreamService = Depends(lambda: job_stream_service),
):
    """Stream real-time job output via Server-Sent Events"""
    return await stream_svc.stream_job_output(job_id)


@router.delete("/{job_id}")
async def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    job_svc: JobService = Depends(lambda: job_service),
):
    """Cancel a running job"""
    success = await job_svc.cancel_job(job_id, db)
    if success:
        return {"message": "Job cancelled successfully"}
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/manager/stats")
def get_job_manager_stats(
    job_manager: BorgJobManager = Depends(get_job_manager_dependency),
):
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


@router.post("/manager/cleanup")
def cleanup_completed_jobs(
    job_manager: BorgJobManager = Depends(get_job_manager_dependency),
):
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
def get_queue_stats(job_manager: BorgJobManager = Depends(get_job_manager_dependency)):
    """Get backup queue statistics"""
    return job_manager.get_queue_stats()


@router.post("/migrate")
def run_database_migration(db: Session = Depends(get_db)):
    """Manually trigger database migration for jobs table"""
    try:
        from app.models.database import migrate_job_table

        migrate_job_table()
        return {"message": "Database migration completed successfully"}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
