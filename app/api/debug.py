import asyncio
import json
import logging
from datetime import datetime, UTC
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.dependencies import DebugServiceDep, JobManagerDep

router = APIRouter(prefix="/api/debug", tags=["debug"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


@router.get("/info")
async def get_debug_info(debug_svc: DebugServiceDep, db: Session = Depends(get_db)):
    """Get comprehensive debug information"""
    try:
        debug_info = await debug_svc.get_debug_info(db)
        return debug_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/html", response_class=HTMLResponse)
async def get_debug_html(
    request: Request, debug_svc: DebugServiceDep, db: Session = Depends(get_db)
):
    """Get debug information as HTML"""
    try:
        debug_info = await debug_svc.get_debug_info(db)
        return templates.TemplateResponse(
            request,
            "partials/debug/debug_panel.html",
            {"debug_info": debug_info},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs-memory-stream")
async def stream_jobs_memory(job_manager: JobManagerDep):
    """Stream real-time updates of jobs in JobManager memory"""
    return StreamingResponse(
        _generate_jobs_memory_stream(job_manager),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def _generate_jobs_memory_stream(job_manager) -> AsyncGenerator[str, None]:
    """Generate Server-Sent Events for jobs in memory"""
    try:
        logger.info("Starting jobs memory stream")

        # Send initial job list
        yield await _format_jobs_list_event(job_manager)

        # Subscribe to job manager events for live updates
        event_queue = job_manager.subscribe_to_events()

        try:
            while True:
                try:
                    # Wait for events with a timeout to send periodic updates
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)

                    # Handle different event types
                    if event.get("type") in ["job_started", "job_completed", "job_failed", "job_cancelled"]:
                        # Send updated job list when job status changes
                        yield await _format_jobs_list_event(job_manager)

                except asyncio.TimeoutError:
                    # Send periodic updates to show current state
                    yield await _format_jobs_list_event(job_manager)

                except Exception as e:
                    logger.error(f"Error in jobs memory stream: {e}")
                    yield f"data: {json.dumps({'error': 'An internal error occurred.'})}\n\n"

        finally:
            job_manager.unsubscribe_from_events(event_queue)

    except Exception as e:
        logger.error(f"Fatal error in jobs memory stream: {e}")
        yield f"data: {json.dumps({'error': 'A fatal stream error occurred.'})}\n\n"


async def _format_jobs_list_event(job_manager) -> str:
    """Format the current jobs list as an SSE event"""
    try:
        jobs_data = []

        # Get current jobs from job manager memory
        for job_id, job in job_manager.jobs.items():
            job_data = {
                "id": job_id,
                "short_id": job_id[:8] + "..." if len(job_id) > 11 else job_id,
                "status": job.status,
                "job_type": getattr(job, "job_type", "unknown"),
                "started_at": job.started_at.strftime("%H:%M:%S") if job.started_at else "N/A",
                "duration": _calculate_duration(job.started_at, job.completed_at),
                "tasks_info": ""
            }

            if hasattr(job, "tasks"):
                current_task = job.current_task_index + 1 if hasattr(job, "current_task_index") else 1
                total_tasks = len(job.tasks) if hasattr(job, "tasks") else 0
                job_data["tasks_info"] = f"{current_task}/{total_tasks}"

                # Get current task name if available
                if hasattr(job, "get_current_task"):
                    current_task_obj = job.get_current_task()
                    if current_task_obj and hasattr(current_task_obj, "task_name"):
                        job_data["current_task_name"] = current_task_obj.task_name

            jobs_data.append(job_data)

        # Generate HTML for the jobs table
        if jobs_data:
            html_content = _generate_jobs_table_html(jobs_data)
        else:
            html_content = '''
                <div class="flex items-center justify-center py-8 text-gray-500 dark:text-gray-400">
                    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2M4 13h2m13-8V4a1 1 0 00-1-1H7a1 1 0 00-1 1v1m8 0V4.5"></path>
                    </svg>
                    No jobs currently in memory
                </div>
            '''

        return f"event: jobs-list\ndata: {html_content}\n\n"

    except Exception as e:
        logger.error(f"Error formatting jobs list: {e}")
        return f"event: jobs-list\ndata: <div class='text-red-600'>Error loading jobs: {str(e)}</div>\n\n"


def _generate_jobs_table_html(jobs_data) -> str:
    """Generate HTML table for jobs data"""
    html = '''
    <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-600">
            <thead class="bg-gray-50 dark:bg-gray-600">
                <tr>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Job ID</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Type</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Started</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Duration</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Tasks</th>
                </tr>
            </thead>
            <tbody class="bg-white dark:bg-gray-700 divide-y divide-gray-200 dark:divide-gray-600">
    '''

    for job in jobs_data:
        status_color = _get_status_color(job["status"])
        html += f'''
                <tr>
                    <td class="px-3 py-2 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-100">{job["short_id"]}</td>
                    <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{job["job_type"]}</td>
                    <td class="px-3 py-2 whitespace-nowrap">
                        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full {status_color}">{job["status"]}</span>
                    </td>
                    <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{job["started_at"]}</td>
                    <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{job["duration"]}</td>
                    <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300">{job["tasks_info"]}</td>
                </tr>
        '''

    html += '''
            </tbody>
        </table>
    </div>
    '''

    return html


def _get_status_color(status: str) -> str:
    """Get CSS classes for job status color"""
    status_colors = {
        "running": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
        "completed": "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
        "failed": "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
        "cancelled": "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
        "queued": "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
        "pending": "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
    }
    return status_colors.get(status, "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200")


def _calculate_duration(started_at, completed_at) -> str:
    """Calculate job duration"""
    if not started_at:
        return "N/A"

    end_time = completed_at or datetime.now(UTC)
    duration = end_time - started_at

    total_seconds = int(duration.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"
