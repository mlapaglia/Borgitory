import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, TYPE_CHECKING, cast
from fastapi.responses import StreamingResponse

from borgitory.protocols import JobManagerProtocol

if TYPE_CHECKING:
    from borgitory.services.jobs.broadcaster.job_event import JobEvent

logger = logging.getLogger(__name__)


class JobStreamService:
    """Service for handling Server-Sent Events streaming for jobs"""

    def __init__(self, job_manager: JobManagerProtocol) -> None:
        self.job_manager = job_manager

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
                if job.tasks:  # All jobs are composite now, check if they have tasks
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
                            "progress": None,
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
                # Cast to JobEvent since it's imported under TYPE_CHECKING
                job_event = cast("JobEvent", event)
                event_type = job_event.event_type.value
                yield f"event: {event_type}\\ndata: {json.dumps(job_event.to_dict())}\\n\\n"

        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\\n\\n"

    async def _job_output_event_generator(
        self, job_id: str
    ) -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for a specific job's output"""
        try:
            logger.debug(f"Starting SSE stream for job {job_id}")

            # Check if this is a composite job first - look in unified manager
            job = self.job_manager.jobs.get(job_id)

            if not job:
                logger.warning(f"Job {job_id} not found in memory - cannot stream")
                yield f"data: {json.dumps({'type': 'error', 'message': f'Job {job_id} not found or not active'})}\n\n"
                return

            if job.tasks:  # All jobs are composite now
                # Stream composite job output from unified manager
                event_queue = self.job_manager.subscribe_to_events()

                try:
                    # Send initial state
                    yield f"data: {json.dumps({'type': 'initial_state', 'job_id': job_id, 'status': job.status})}\n\n"

                    # Stream events
                    while True:
                        try:
                            if event_queue is None:
                                break
                            event = await asyncio.wait_for(
                                event_queue.get(), timeout=30.0
                            )
                            # event is already JobEvent type
                            # Only send events for this job
                            if event.job_id == job_id:
                                # Handle different event types for HTMX SSE
                                if event.event_type.value == "task_output":
                                    # Send task-specific output for HTMX sse-swap
                                    task_index_raw = (
                                        event.data.get("task_index", 0)
                                        if event.data
                                        else 0
                                    )
                                    task_index = (
                                        int(task_index_raw)
                                        if isinstance(task_index_raw, (int, str))
                                        else 0
                                    )
                                    output_line = (
                                        event.data.get("line", "") if event.data else ""
                                    )

                                    # Get current task and build accumulated output
                                    if hasattr(job, "tasks") and task_index < len(
                                        job.tasks
                                    ):
                                        task = job.tasks[task_index]
                                        if (
                                            hasattr(task, "output_lines")
                                            and task.output_lines
                                        ):
                                            # Build complete output from all lines
                                            full_output = "\n".join(
                                                [
                                                    line.get("text", "")
                                                    if isinstance(line, dict)
                                                    else str(line)
                                                    for line in task.output_lines
                                                ]
                                            )
                                            # Send complete accumulated output
                                            yield f"event: task-{task_index}-output\ndata: {full_output}\n\n"
                                        else:
                                            # Fall back to single line
                                            yield f"event: task-{task_index}-output\ndata: {output_line}\n\n"
                                    else:
                                        # Fall back to single line
                                        yield f"event: task-{task_index}-output\ndata: {output_line}\n\n"

                                elif event.event_type.value == "task_started":
                                    task_index_raw = (
                                        event.data.get("task_index", 0)
                                        if event.data
                                        else 0
                                    )
                                    task_index = (
                                        int(task_index_raw)
                                        if isinstance(task_index_raw, (int, str))
                                        else 0
                                    )
                                    status_badge = '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">⟳ Running</span>'
                                    yield f"event: task-{task_index}-status\ndata: {status_badge}\n\n"

                                elif event.event_type.value == "task_completed":
                                    task_index_raw = (
                                        event.data.get("task_index", 0)
                                        if event.data
                                        else 0
                                    )
                                    task_index = (
                                        int(task_index_raw)
                                        if isinstance(task_index_raw, (int, str))
                                        else 0
                                    )
                                    status_badge = '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">✓ Completed</span>'
                                    yield f"event: task-{task_index}-status\ndata: {status_badge}\n\n"

                                elif event.event_type.value == "task_failed":
                                    task_index_raw = (
                                        event.data.get("task_index", 0)
                                        if event.data
                                        else 0
                                    )
                                    task_index = (
                                        int(task_index_raw)
                                        if isinstance(task_index_raw, (int, str))
                                        else 0
                                    )
                                    status_badge = '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">✗ Failed</span>'
                                    yield f"event: task-{task_index}-status\ndata: {status_badge}\n\n"

                                elif event.event_type.value == "job_completed":
                                    # Send complete event to trigger switch to static view
                                    yield "event: complete\ndata: completed\n\n"

                                else:
                                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                        except asyncio.TimeoutError:
                            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                            break
                finally:
                    if event_queue:
                        self.job_manager.unsubscribe_from_events(event_queue)
            else:
                # Stream regular borg job output
                logger.info(f"Starting regular job output stream for {job_id}")
                output_buffer = []

                try:
                    async for output_event in self.job_manager.stream_job_output(
                        job_id
                    ):
                        # output_event is Dict[str, object] from stream_job_output method
                        logger.debug(f"Job {job_id} received event: {output_event}")

                        if output_event.get("type") == "output":
                            # Accumulate output lines
                            line_data = output_event.get("data", "")
                            if isinstance(line_data, dict):
                                output_buffer.append(line_data.get("text", ""))
                            else:
                                output_buffer.append(str(line_data))

                            # Send accumulated output for HTMX sse-swap
                            full_output = "\n".join(output_buffer)
                            yield f"event: output\ndata: {full_output}\n\n"

                            # Also send status update if there's progress
                            if output_event.get("progress"):
                                yield "event: output-status\ndata: Streaming\n\n"
                        elif output_event.get("type") == "complete":
                            # Send completion event to trigger switch to static view
                            logger.info(
                                f"Job {job_id} completed, sending completion event"
                            )
                            yield "event: complete\ndata: completed\n\n"
                            break
                        else:
                            # Send other events as JSON data
                            yield f"data: {json.dumps(output_event)}\n\n"
                except Exception as stream_error:
                    logger.error(
                        f"Error in job output stream for {job_id}: {stream_error}"
                    )
                    yield f"event: output\ndata: Error streaming output: {stream_error}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    async def stream_task_output(
        self, job_id: str, task_order: int
    ) -> StreamingResponse:
        """Stream real-time output for a specific task via Server-Sent Events"""
        return StreamingResponse(
            self._task_output_event_generator(job_id, task_order),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    async def _task_output_event_generator(
        self, job_id: str, task_order: int
    ) -> AsyncGenerator[str, None]:
        """Generate Server-Sent Events for a specific task's output"""
        try:
            logger.debug(
                f"Starting task SSE stream for job {job_id}, task {task_order}"
            )

            # Get the job from manager - only stream from memory
            job = self.job_manager.jobs.get(job_id)
            if not job:
                logger.warning(f"Job {job_id} not found in memory - cannot stream")
                yield f"event: error\ndata: Job {job_id} not found or not active\n\n"
                return

            # All jobs are now composite, just check if they have tasks
            if not hasattr(job, "tasks") or not job.tasks:
                yield f"event: error\ndata: Job {job_id} has no tasks to stream\n\n"
                return

            # Find the specific task
            if not hasattr(job, "tasks") or task_order >= len(job.tasks):
                yield f"event: error\ndata: Task {task_order} not found in job {job_id}\n\n"
                return

            task = job.tasks[task_order]
            logger.info(
                f"Found task {task_order} in job {job_id}: {task.task_name}, status: {task.status}"
            )

            # Validate task status consistency with job
            if task.status in ["completed", "failed"] and job.status == "running":
                logger.warning(
                    f"Task {task_order} is {task.status} but job {job_id} is still running - this may be normal during transitions"
                )

            # Subscribe to events for this job
            event_queue = self.job_manager.subscribe_to_events()

            try:
                # Send current task output if any (for existing lines when connection starts)
                if hasattr(task, "output_lines") and task.output_lines:
                    # Send each existing line as individual output events
                    for line in task.output_lines:
                        # Handle both dict format {"text": "content"} and plain string format
                        if isinstance(line, dict):
                            line_text = line.get("text", "")
                        else:
                            line_text = str(line)

                        if line_text.strip():
                            # Send individual line as div for beforeend appending
                            yield f"event: output\ndata: <div>{line_text}</div>\n\n"

                # Stream live updates
                while task.status == "running":
                    try:
                        if event_queue is None:
                            break
                        event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                        # event is already JobEvent type
                        logger.debug(
                            f"Task streaming received event: {event.event_type.value} for job {event.job_id or 'unknown'}"
                        )

                        # Only process events for this specific job and task
                        if (
                            event.job_id == job_id
                            and event.event_type.value == "job_output"
                        ):
                            event_data = event.data or {}
                            # Check if this is a task-specific event for our task
                            event_task_index = event_data.get("task_index")
                            logger.debug(
                                f"Event task_index: {event_task_index}, expected: {task_order}"
                            )

                            if event_task_index == task_order:
                                output_line_raw = event_data.get("line", "")
                                output_line = (
                                    str(output_line_raw) if output_line_raw else ""
                                )
                                if output_line:
                                    # Send individual line as div for hx-swap="beforeend"
                                    logger.debug(
                                        f"Sending output line for task {task_order}: {output_line[:50]}..."
                                    )
                                    yield f"event: output\ndata: <div>{output_line}</div>\n\n"

                        elif (
                            event.job_id == job_id
                            and event.event_type.value
                            in ["task_completed", "task_failed"]
                            and event.data
                            and event.data.get("task_index") == task_order
                        ):
                            # Task completed or failed
                            logger.info(
                                f"Task {task_order} in job {job_id} {event.event_type.value}"
                            )
                            yield f"event: complete\ndata: {event.event_type.value}\n\n"
                            break

                    except asyncio.TimeoutError:
                        # Send heartbeat
                        yield "event: heartbeat\ndata: ping\n\n"
                        continue

                # Send final completion if task is no longer running
                if task.status != "running":
                    yield f"event: complete\ndata: {task.status}\n\n"

            finally:
                if event_queue:
                    self.job_manager.unsubscribe_from_events(event_queue)

        except Exception as e:
            logger.error(
                f"Error in task output stream for job {job_id}, task {task_order}: {e}",
                exc_info=True,
            )
            # Send error event with more specific information
            error_msg = f"Streaming error for job {job_id}, task {task_order}: {str(e)}"
            yield f"event: error\ndata: {error_msg}\n\n"

    async def get_job_status(self, job_id: str) -> Dict[str, object]:
        """Get current job status and progress for streaming"""
        output = await self.job_manager.get_job_output_stream(job_id, last_n_lines=50)
        return output

    def get_current_jobs_data(self) -> list[Dict[str, object]]:
        """Get current running jobs data for rendering"""
        current_jobs: list[Dict[str, object]] = []

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

                current_jobs.append(
                    {
                        "id": job_id,
                        "type": job_type,
                        "status": borg_job.status,
                        "started_at": borg_job.started_at.strftime("%H:%M:%S"),
                        "progress": {},
                        "progress_info": progress_info,
                    }
                )

        # Get current composite jobs from unified manager
        for job_id, job in self.job_manager.jobs.items():
            if job.tasks and job.status == "running":  # All jobs are composite now
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
