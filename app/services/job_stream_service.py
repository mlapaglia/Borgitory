import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any
from fastapi.responses import StreamingResponse

from app.services.job_manager import get_job_manager

logger = logging.getLogger(__name__)


class JobStreamService:
    """Service for handling Server-Sent Events streaming for jobs"""

    def __init__(self, job_manager=None):
        self.job_manager = job_manager or get_job_manager()

    async def stream_all_jobs(self) -> StreamingResponse:
        """Stream real-time updates for all jobs via Server-Sent Events"""
        return StreamingResponse(
            self._all_jobs_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control",
            },
        )

    async def stream_job_output(self, job_id: str) -> StreamingResponse:
        """Stream real-time job output via Server-Sent Events"""
        return StreamingResponse(
            self._job_output_event_generator(job_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    async def _all_jobs_event_generator(self) -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for all job updates"""
        try:
            # Send initial job list (both simple and composite jobs from unified manager)
            jobs_data = []

            # Add all jobs from unified manager
            for job_id, job in self.job_manager.jobs.items():
                if job.is_composite():
                    # Composite job
                    jobs_data.append(
                        {
                            "id": job_id,
                            "type": "composite_job_status",
                            "status": job.status,
                            "started_at": job.started_at.isoformat(),
                            "completed_at": job.completed_at.isoformat()
                            if job.completed_at
                            else None,
                            "current_task_index": job.current_task_index,
                            "total_tasks": len(job.tasks),
                            "job_type": job.job_type
                            if hasattr(job, "job_type")
                            else "composite",
                        }
                    )
                else:
                    # Simple job
                    command_display = ""
                    if job.command:
                        command_display = (
                            " ".join(job.command[:3]) + "..."
                            if len(job.command) > 3
                            else " ".join(job.command)
                        )

                    jobs_data.append(
                        {
                            "id": job_id,
                            "type": "job_status",
                            "status": job.status,
                            "started_at": job.started_at.isoformat(),
                            "completed_at": job.completed_at.isoformat()
                            if job.completed_at
                            else None,
                            "return_code": job.return_code,
                            "error": job.error,
                            "progress": job.current_progress,
                            "command": command_display,
                        }
                    )

            if jobs_data:
                yield f"event: jobs_update\\ndata: {json.dumps({'type': 'jobs_update', 'jobs': jobs_data})}\\n\\n"
            else:
                yield f"event: jobs_update\\ndata: {json.dumps({'type': 'jobs_update', 'jobs': []})}\\n\\n"

            # Stream job updates from borg job manager only
            # Individual task output should come from /api/jobs/{job_id}/stream
            async for event in self.job_manager.stream_all_job_updates():
                event_type = event.get("type", "unknown")
                yield f"event: {event_type}\\ndata: {json.dumps(event)}\\n\\n"

        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\\n\\n"

    async def _job_output_event_generator(
        self, job_id: str
    ) -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for a specific job's output"""
        try:
            # Check if this is a composite job first - look in unified manager
            job = self.job_manager.jobs.get(job_id)
            if job and job.is_composite():
                # Stream composite job output from unified manager
                event_queue = self.job_manager.subscribe_to_events()

                try:
                    # Send initial state
                    yield f"data: {json.dumps({'type': 'initial_state', 'job_id': job_id, 'status': job.status})}\n\n"

                    # Stream events
                    while True:
                        try:
                            event = await asyncio.wait_for(
                                event_queue.get(), timeout=30.0
                            )
                            # Only send events for this job
                            if event.get("job_id") == job_id:
                                yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.TimeoutError:
                            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                            break
                finally:
                    self.job_manager.unsubscribe_from_events(event_queue)
            else:
                # Stream regular borg job output
                async for event in self.job_manager.stream_job_output(job_id):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current job status and progress for streaming"""
        output = await self.job_manager.get_job_output_stream(job_id, last_n_lines=50)
        return output

    def get_current_jobs_data(self) -> list[Dict[str, Any]]:
        """Get current running jobs data for rendering"""
        current_jobs = []

        # Get current jobs from JobManager (simple borg jobs)
        for job_id, borg_job in self.job_manager.jobs.items():
            if borg_job.status == "running":
                # Determine job type from command
                job_type = "unknown"
                if borg_job.command and len(borg_job.command) > 1:
                    if "create" in borg_job.command:
                        job_type = "backup"
                    elif "list" in borg_job.command:
                        job_type = "list"
                    elif "check" in borg_job.command:
                        job_type = "verify"

                # Calculate progress info
                progress_info = ""
                if borg_job.current_progress:
                    if "files" in borg_job.current_progress:
                        progress_info = f"Files: {borg_job.current_progress['files']}"
                    if "transferred" in borg_job.current_progress:
                        progress_info += (
                            f" | {borg_job.current_progress['transferred']}"
                        )

                current_jobs.append(
                    {
                        "id": job_id,
                        "type": job_type,
                        "status": borg_job.status,
                        "started_at": borg_job.started_at.strftime("%H:%M:%S"),
                        "progress": borg_job.current_progress,
                        "progress_info": progress_info,
                    }
                )

        # Get current composite jobs from unified manager
        for job_id, job in self.job_manager.jobs.items():
            if job.is_composite() and job.status == "running":
                # Get current task info
                current_task = job.get_current_task()

                progress_info = f"Task: {current_task.task_name if current_task else 'Unknown'} ({job.current_task_index + 1}/{len(job.tasks)})"

                current_jobs.append(
                    {
                        "id": job_id,
                        "type": getattr(job, "job_type", "composite"),
                        "status": job.status,
                        "started_at": job.started_at.strftime("%H:%M:%S"),
                        "progress": {
                            "current_task": current_task.task_name
                            if current_task
                            else "Unknown",
                            "task_progress": f"{job.current_task_index + 1}/{len(job.tasks)}",
                        },
                        "progress_info": progress_info,
                    }
                )

        return current_jobs


# Global instance for dependency injection
job_stream_service = JobStreamService()
