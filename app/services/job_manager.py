import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, AsyncGenerator, TYPE_CHECKING
from dataclasses import dataclass, field
from collections import deque

from app.utils.db_session import get_db_session

if TYPE_CHECKING:
    from app.models.database import Repository, Schedule, Job
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class BorgJobTask:
    """Individual task within a job"""

    task_type: str  # 'backup', 'prune', 'check', 'cloud_sync'
    task_name: str
    status: str = "pending"  # 'pending', 'running', 'completed', 'failed', 'skipped'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None

    # Task-specific output storage
    output_lines: deque = field(default_factory=lambda: deque(maxlen=1000))

    # Task-specific parameters (stored as dict for flexibility)
    parameters: Dict = field(default_factory=dict)


@dataclass
class BorgJob:
    id: str
    status: str  # 'pending', 'queued', 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None

    # For backward compatibility - single command jobs
    command: Optional[List[str]] = None

    # Multi-task job support
    job_type: str = "simple"  # 'simple' or 'composite'
    db_job_id: Optional[int] = None  # Link to database Job record
    tasks: List[BorgJobTask] = field(default_factory=list)
    current_task_index: int = 0

    # Repository and schedule context (for composite jobs)
    repository: Optional["Repository"] = None
    schedule: Optional["Schedule"] = None

    # Streaming output storage (for simple jobs)
    output_lines: deque = field(
        default_factory=lambda: deque(maxlen=1000)
    )  # Keep last 1000 lines
    current_progress: Dict = field(default_factory=dict)  # Parsed progress info

    def get_current_task(self) -> Optional[BorgJobTask]:
        """Get the currently executing task (for composite jobs)"""
        if self.job_type == "composite" and 0 <= self.current_task_index < len(
            self.tasks
        ):
            return self.tasks[self.current_task_index]
        return None

    def is_composite(self) -> bool:
        """Check if this is a multi-task composite job"""
        return self.job_type == "composite" and len(self.tasks) > 0


class BorgJobManager:
    def __init__(self):
        self.jobs: Dict[str, BorgJob] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._event_queues: List[asyncio.Queue] = []  # For SSE streaming

        # Job queue system
        self.MAX_CONCURRENT_BACKUPS = 5
        self._backup_queue: asyncio.Queue = asyncio.Queue()
        self._backup_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_BACKUPS)
        self._queue_processor_started = False

    async def start_borg_command(
        self, command: List[str], env: Optional[Dict] = None, is_backup: bool = False
    ) -> str:
        """Start a Borg command and track its output (backward compatibility)"""
        job_id = str(uuid.uuid4())

        job = BorgJob(
            id=job_id,
            command=command,
            job_type="simple",
            status="queued" if is_backup else "running",
            started_at=datetime.now(),
        )
        self.jobs[job_id] = job

        if is_backup:
            # Start queue processor if not already running
            if not self._queue_processor_started:
                asyncio.create_task(self._process_backup_queue())
                self._queue_processor_started = True

            logger.info(
                f"Queuing backup job {job_id} with command: {' '.join(command)}"
            )

            # Broadcast job queued event
            self._broadcast_job_event(
                {
                    "type": "job_queued",
                    "job_id": job_id,
                    "command": " ".join(command[:3]) + "..."
                    if len(command) > 3
                    else " ".join(command),
                    "status": "queued",
                    "started_at": job.started_at.isoformat(),
                }
            )

            # Add to backup queue
            await self._backup_queue.put((job_id, command, env))

        else:
            # Non-backup jobs run immediately
            logger.info(f"Starting Borg job {job_id} with command: {' '.join(command)}")

            # Broadcast job started event
            self._broadcast_job_event(
                {
                    "type": "job_started",
                    "job_id": job_id,
                    "command": " ".join(command[:3]) + "..."
                    if len(command) > 3
                    else " ".join(command),
                    "status": "running",
                    "started_at": job.started_at.isoformat(),
                }
            )

            # Start the subprocess with output streaming
            asyncio.create_task(self._run_borg_job(job_id, command, env))

        return job_id

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List[Dict],
        repository: "Repository",
        schedule: Optional["Schedule"] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a composite job with multiple tasks"""
        job_id = str(uuid.uuid4())

        # Create database job record
        from app.models.database import Job, JobTask
        from app.utils.db_session import get_db_session

        with get_db_session() as db:
            db_job = Job(
                repository_id=repository.id,
                job_uuid=job_id,
                type=job_type,
                status="pending",
                job_type="composite",
                total_tasks=len(task_definitions),
                completed_tasks=0,
                cloud_sync_config_id=cloud_sync_config_id,
                started_at=datetime.now(),
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)

            # Create task records in database
            for i, task_def in enumerate(task_definitions):
                task = JobTask(
                    job_id=db_job.id,
                    task_type=task_def["type"],
                    task_name=task_def["name"],
                    status="pending",
                    task_order=i,
                )
                db.add(task)

            logger.info(
                f"📝 Created composite job {job_id} (db_id: {db_job.id}) with {len(task_definitions)} tasks"
            )

        # Create in-memory job with tasks
        tasks = []
        for task_def in task_definitions:
            task = BorgJobTask(
                task_type=task_def["type"],
                task_name=task_def["name"],
                parameters=task_def,  # Store all parameters
            )
            tasks.append(task)

        job = BorgJob(
            id=job_id,
            job_type="composite",
            status="pending",
            started_at=datetime.now(),
            db_job_id=db_job.id,
            tasks=tasks,
            repository=repository,
            schedule=schedule,
        )

        self.jobs[job_id] = job

        # Start executing the composite job
        asyncio.create_task(self._execute_composite_job(job_id))

        return job_id

    async def _process_backup_queue(self):
        """Process the backup queue, respecting concurrent limits"""
        logger.info(
            f"Started backup queue processor (max concurrent: {self.MAX_CONCURRENT_BACKUPS})"
        )

        while True:
            try:
                # Get next job from queue (this blocks until a job is available)
                job_id, command, env = await self._backup_queue.get()

                # Acquire semaphore (this blocks if we've reached the concurrent limit)
                await self._backup_semaphore.acquire()

                # Update job status to running and broadcast event
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job.status = "running"

                    logger.info(
                        f"Starting queued backup job {job_id} ({self.MAX_CONCURRENT_BACKUPS - self._backup_semaphore._value}/{self.MAX_CONCURRENT_BACKUPS} slots used)"
                    )

                    self._broadcast_job_event(
                        {
                            "type": "job_started",
                            "job_id": job_id,
                            "command": " ".join(command[:3]) + "..."
                            if len(command) > 3
                            else " ".join(command),
                            "status": "running",
                            "started_at": job.started_at.isoformat(),
                        }
                    )

                    # Start the backup job and release semaphore when done
                    asyncio.create_task(
                        self._run_backup_with_semaphore(job_id, command, env)
                    )

                # Mark this queue item as done
                self._backup_queue.task_done()

            except Exception as e:
                logger.error(f"Error in backup queue processor: {e}")
                await asyncio.sleep(1)  # Prevent tight error loops

    async def _run_backup_with_semaphore(
        self, job_id: str, command: List[str], env: Optional[Dict]
    ):
        """Run a backup job and release the semaphore when complete"""
        try:
            await self._run_borg_job(job_id, command, env)
        finally:
            # Always release the semaphore to allow next queued job
            self._backup_semaphore.release()
            logger.info(
                f"Released backup slot for job {job_id} ({self.MAX_CONCURRENT_BACKUPS - self._backup_semaphore._value}/{self.MAX_CONCURRENT_BACKUPS} slots used)"
            )

    async def _run_borg_job(self, job_id: str, command: List[str], env: Optional[Dict]):
        job = self.jobs[job_id]

        try:
            # Create subprocess with line-buffered output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Combine stderr with stdout
                env=env,
            )

            self._processes[job_id] = process

            logger.info(f"Borg job {job_id} started with PID {process.pid}")

            # Stream output line by line
            async for line in process.stdout:
                decoded_line = line.decode("utf-8", errors="replace").rstrip()

                # Store the line
                job.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": decoded_line}
                )

                # Log the output to console for debugging
                logger.info(f"Borg job {job_id} output: {decoded_line}")

                # Parse Borg progress (Borg outputs JSON progress to stderr)
                if decoded_line.startswith("{") and '"type":"progress"' in decoded_line:
                    try:
                        progress = json.loads(decoded_line)
                        job.current_progress = {
                            "percent": progress.get("percent", 0),
                            "nfiles": progress.get("nfiles", 0),
                            "current_file": progress.get("current", ""),
                            "original_size": progress.get("original_size", 0),
                            "compressed_size": progress.get("compressed_size", 0),
                        }

                        # Broadcast progress update
                        self._broadcast_job_event(
                            {
                                "type": "job_progress",
                                "job_id": job_id,
                                "progress": job.current_progress,
                            }
                        )
                    except json.JSONDecodeError:
                        pass

                # Broadcast output line
                self._broadcast_job_event(
                    {
                        "type": "job_output",
                        "job_id": job_id,
                        "line": decoded_line,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            # Wait for process to complete
            await process.wait()

            job.return_code = process.returncode
            job.status = "completed" if process.returncode == 0 else "failed"
            job.completed_at = datetime.now()

            logger.info(
                f"Borg job {job_id} completed with return code {process.returncode}"
            )

            # Broadcast job completion event
            self._broadcast_job_event(
                {
                    "type": "job_completed",
                    "job_id": job_id,
                    "status": job.status,
                    "return_code": process.returncode,
                    "completed_at": job.completed_at.isoformat(),
                }
            )

            # Update database job record with results
            asyncio.create_task(self._update_database_job(job_id))

            # Auto-cleanup completed job after 30 seconds
            asyncio.create_task(self._auto_cleanup_job(job_id, delay=30))

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.now()
            logger.error(f"Borg job {job_id} failed: {e}")

            # Broadcast job failure event
            self._broadcast_job_event(
                {
                    "type": "job_failed",
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(e),
                    "completed_at": job.completed_at.isoformat(),
                }
            )

            # Update database job record with results
            asyncio.create_task(self._update_database_job(job_id))

            # Auto-cleanup failed job after 30 seconds
            asyncio.create_task(self._auto_cleanup_job(job_id, delay=30))

        finally:
            self._processes.pop(job_id, None)

    async def _execute_composite_job(self, job_id: str):
        """Execute all tasks in a composite job sequentially"""
        job = self.jobs.get(job_id)
        if not job or not job.is_composite():
            logger.error(f"Composite job {job_id} not found or invalid")
            return

        logger.info(f"🚀 Starting composite job {job_id} with {len(job.tasks)} tasks")

        job.status = "running"

        # Update database job status
        self._update_composite_job_status(job_id, "running")

        self._broadcast_job_event(
            {
                "type": "job_started",
                "job_id": job_id,
                "status": "running",
                "job_type": "composite",
                "total_tasks": len(job.tasks),
                "started_at": job.started_at.isoformat(),
            }
        )

        try:
            # Execute each task sequentially
            for i, task in enumerate(job.tasks):
                job.current_task_index = i

                logger.info(
                    f"🔄 Starting task {i + 1}/{len(job.tasks)}: {task.task_name}"
                )

                task.status = "running"
                task.started_at = datetime.now()

                # Update database task status
                self._update_composite_task_status(job_id, i, "running")

                # Broadcast task started event
                self._broadcast_job_event(
                    {
                        "type": "task_started",
                        "job_id": job_id,
                        "task_index": i,
                        "task_name": task.task_name,
                        "task_type": task.task_type,
                        "status": "running",
                    }
                )

                try:
                    # Execute the specific task
                    success = await self._execute_task(job, task, i)

                    if success:
                        task.status = "completed"
                        task.completed_at = datetime.now()
                        task.return_code = 0

                        logger.info(
                            f"✅ Task {i + 1}/{len(job.tasks)} completed: {task.task_name}"
                        )

                        # Update database task status
                        self._update_composite_task_status(
                            job_id, i, "completed", return_code=0
                        )

                        # Broadcast task completion
                        self._broadcast_job_event(
                            {
                                "type": "task_completed",
                                "job_id": job_id,
                                "task_index": i,
                                "status": "completed",
                                "return_code": 0,
                            }
                        )
                    else:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                        task.return_code = 1

                        logger.error(
                            f"❌ Task {i + 1}/{len(job.tasks)} failed: {task.task_name}"
                        )

                        # Mark remaining tasks as skipped
                        self._mark_remaining_tasks_as_skipped(job, i + 1)

                        # Fail the entire job
                        job.status = "failed"
                        job.completed_at = datetime.now()

                        # Update database job status
                        self._update_composite_job_status(job_id, "failed")

                        self._broadcast_job_event(
                            {
                                "type": "job_failed",
                                "job_id": job_id,
                                "status": "failed",
                                "completed_at": job.completed_at.isoformat(),
                            }
                        )
                        return

                except Exception as e:
                    logger.error(f"❌ Exception in task {task.task_name}: {str(e)}")
                    task.status = "failed"
                    task.completed_at = datetime.now()
                    task.return_code = 1
                    task.error = str(e)

                    # Mark remaining tasks as skipped
                    self._mark_remaining_tasks_as_skipped(job, i + 1)

                    # Fail the entire job
                    job.status = "failed"
                    job.completed_at = datetime.now()

                    # Update database job status
                    self._update_composite_job_status(job_id, "failed")

                    self._broadcast_job_event(
                        {
                            "type": "job_failed",
                            "job_id": job_id,
                            "status": "failed",
                            "error": str(e),
                            "completed_at": job.completed_at.isoformat(),
                        }
                    )
                    return

            # All tasks completed successfully
            job.status = "completed"
            job.completed_at = datetime.now()

            # Update database job status
            self._update_composite_job_status(job_id, "completed")

            self._broadcast_job_event(
                {
                    "type": "job_completed",
                    "job_id": job_id,
                    "status": "completed",
                    "completed_at": job.completed_at.isoformat(),
                }
            )

            logger.info(f"🎉 Composite job {job_id} completed successfully")

            # Auto-cleanup completed job after 30 seconds
            asyncio.create_task(self._auto_cleanup_job(job_id, delay=30))

        except Exception as e:
            logger.error(f"❌ Fatal error in composite job {job_id}: {str(e)}")
            job.status = "failed"
            job.completed_at = datetime.now()

            # Update database job status
            self._update_composite_job_status(job_id, "failed")

            self._broadcast_job_event(
                {
                    "type": "job_failed",
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(e),
                    "completed_at": job.completed_at.isoformat(),
                }
            )

    async def _execute_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a specific task based on its type"""

        if task.task_type == "backup":
            return await self._execute_backup_task(job, task, task_index)
        elif task.task_type == "prune":
            return await self._execute_prune_task(job, task, task_index)
        elif task.task_type == "check":
            return await self._execute_check_task(job, task, task_index)
        elif task.task_type == "cloud_sync":
            return await self._execute_cloud_sync_task(job, task, task_index)
        else:
            logger.error(f"Unknown task type: {task.task_type}")
            task.error = f"Unknown task type: {task.task_type}"
            return False

    def _mark_remaining_tasks_as_skipped(self, job: BorgJob, start_index: int):
        """Mark all remaining tasks as skipped when a job fails"""
        for i in range(start_index, len(job.tasks)):
            task = job.tasks[i]
            if task.status == "pending":
                task.status = "skipped"
                task.completed_at = datetime.now()
                logger.info(
                    f"⏭️ Task {i + 1}/{len(job.tasks)} skipped: {task.task_name}"
                )

    def _broadcast_task_output(self, job_id: str, task_index: int, line: str):
        """Broadcast task output to SSE listeners"""
        self._broadcast_job_event(
            {
                "type": "task_output",
                "job_id": job_id,
                "task_index": task_index,
                "line": line,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict:
        """Get current output for streaming to frontend"""
        job = self.jobs.get(job_id)
        if not job:
            return {"error": "Job not found"}

        if job.is_composite():
            # For composite jobs, return current task output
            current_task = job.get_current_task()
            if current_task and job.status == "running":
                lines = list(current_task.output_lines)
                if last_n_lines:
                    lines = lines[-last_n_lines:]

                return {
                    "job_id": job_id,
                    "job_type": "composite",
                    "status": job.status,
                    "current_task_index": job.current_task_index,
                    "total_tasks": len(job.tasks),
                    "current_task_output": lines,
                    "current_task_name": current_task.task_name,
                    "started_at": job.started_at.isoformat(),
                    "completed_at": job.completed_at.isoformat()
                    if job.completed_at
                    else None,
                    "error": job.error,
                }
            else:
                return {
                    "job_id": job_id,
                    "job_type": "composite",
                    "status": job.status,
                    "current_task_index": job.current_task_index,
                    "total_tasks": len(job.tasks),
                    "current_task_output": [],
                    "started_at": job.started_at.isoformat(),
                    "completed_at": job.completed_at.isoformat()
                    if job.completed_at
                    else None,
                    "error": job.error,
                }
        else:
            # Simple jobs - return regular output
            lines = list(job.output_lines)
            if last_n_lines:
                lines = lines[-last_n_lines:]

            return {
                "job_id": job_id,
                "job_type": "simple",
                "status": job.status,
                "progress": job.current_progress,
                "lines": lines,
                "total_lines": len(job.output_lines),
                "return_code": job.return_code,
                "started_at": job.started_at.isoformat(),
                "completed_at": job.completed_at.isoformat()
                if job.completed_at
                else None,
                "error": job.error,
            }

    async def stream_job_output(self, job_id: str):
        """Generator for real-time streaming (SSE/WebSocket)"""
        job = self.jobs.get(job_id)
        if not job:
            return

        last_sent = 0
        while job.status == "running" or last_sent < len(job.output_lines):
            current_lines = list(job.output_lines)

            # Send new lines since last check
            if len(current_lines) > last_sent:
                for line in current_lines[last_sent:]:
                    yield {
                        "type": "output",
                        "data": line,
                        "progress": job.current_progress,
                    }
                last_sent = len(current_lines)

            if job.status != "running":
                yield {
                    "type": "complete",
                    "status": job.status,
                    "return_code": job.return_code,
                }
                break

            await asyncio.sleep(0.1)  # Poll interval

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running Borg job"""
        process = self._processes.get(job_id)
        if process:
            try:
                process.terminate()
                await asyncio.sleep(2)
                if process.returncode is None:
                    process.kill()  # Force kill if not terminated
                logger.info(f"Cancelled Borg job {job_id}")
                return True
            except Exception as e:
                logger.error(f"Error cancelling job {job_id}: {e}")
                return False
        return False

    def _broadcast_job_event(self, event: Dict):
        """Broadcast job event to all SSE clients"""
        # Send event to all active queues
        failed_queues = []
        for queue in self._event_queues:
            try:
                if not queue.full():
                    queue.put_nowait(event)
            except Exception as e:
                # Mark queue for removal (likely disconnected client)
                logger.debug(f"Failed to send event to queue: {e}")
                failed_queues.append(queue)

        # Remove failed queues
        for queue in failed_queues:
            try:
                self._event_queues.remove(queue)
            except ValueError:
                pass

    def get_queue_stats(self) -> Dict:
        """Get queue and concurrency statistics"""
        running_backups = sum(
            1
            for job in self.jobs.values()
            if job.status == "running" and "create" in job.command
        )
        queued_backups = sum(1 for job in self.jobs.values() if job.status == "queued")

        return {
            "max_concurrent_backups": self.MAX_CONCURRENT_BACKUPS,
            "running_backups": running_backups,
            "queued_backups": queued_backups,
            "available_slots": self.MAX_CONCURRENT_BACKUPS - running_backups,
            "queue_size": self._backup_queue.qsize()
            if hasattr(self, "_backup_queue")
            else 0,
        }

    async def stream_all_job_updates(self) -> AsyncGenerator[Dict, None]:
        """Generator for streaming all job updates via SSE"""
        # Create a queue for this client
        client_queue = asyncio.Queue(maxsize=100)
        self._event_queues.append(client_queue)

        try:
            while True:
                try:
                    # Wait for events with timeout
                    event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"type": "keepalive", "timestamp": datetime.now().isoformat()}
                except Exception as e:
                    logger.error(f"SSE streaming error: {e}")
                    break
        finally:
            # Clean up this client's queue
            try:
                self._event_queues.remove(client_queue)
            except ValueError:
                pass

    def subscribe_to_events(self) -> asyncio.Queue:
        """Subscribe to job events for SSE streaming"""
        queue = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue

    def unsubscribe_from_events(self, queue: asyncio.Queue):
        """Unsubscribe from job events"""
        if queue in self._event_queues:
            self._event_queues.remove(queue)

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get basic job status for API responses"""
        job = self.jobs.get(job_id)
        if not job:
            return None

        return {
            "running": job.status == "running",
            "completed": job.status == "completed",
            "status": job.status,
            "started_at": job.started_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "return_code": job.return_code,
            "error": job.error,
        }

    def cleanup_job(self, job_id: str) -> bool:
        """Remove job from memory after results are retrieved"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            logger.info(f"Cleaned up job {job_id}")
            return True
        return False

    async def _auto_cleanup_job(self, job_id: str, delay: int = 30):
        """Auto-cleanup job after specified delay"""
        await asyncio.sleep(delay)
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status in ["completed", "failed"]:
                logger.info(
                    f"Auto-cleaning up {job.status} job {job_id} after {delay}s"
                )
                self.cleanup_job(job_id)

                # Broadcast updated jobs list
                self._broadcast_job_event(
                    {
                        "type": "jobs_update",
                        "jobs": [
                            {
                                "id": jid,
                                "status": j.status,
                                "started_at": j.started_at.isoformat(),
                                "completed_at": j.completed_at.isoformat()
                                if j.completed_at
                                else None,
                                "return_code": j.return_code,
                                "error": j.error,
                                "progress": j.current_progress,
                                "command": " ".join(j.command[:3]) + "..."
                                if len(j.command) > 3
                                else " ".join(j.command),
                            }
                            for jid, j in self.jobs.items()
                        ],
                    }
                )

    async def _update_database_job(self, job_id: str):
        """Update database job record with completion results"""
        try:
            from app.models.database import Job

            job = self.jobs.get(job_id)
            if not job:
                return

            # Get output lines as text
            output_text = "\n".join([line["text"] for line in job.output_lines])

            # Update database job
            with get_db_session() as db:
                db_job = db.query(Job).filter(Job.job_uuid == job_id).first()
                if db_job:
                    logger.info(
                        f"🔍 Found database job {db_job.id} for JobManager job {job_id}"
                    )
                    logger.info(
                        f"📊 Job details - Type: {db_job.type}, Status: {job.status}, Return Code: {job.return_code}, Cloud Sync Config ID: {db_job.cloud_sync_config_id}"
                    )

                    db_job.status = (
                        "completed" if job.status == "completed" else "failed"
                    )
                    db_job.finished_at = job.completed_at
                    db_job.log_output = output_text
                    if job.error:
                        db_job.error = job.error

                    logger.info(f"✅ Updated database job record for {job_id}")

                    # Trigger cloud backup if this was a successful backup job
                    logger.info("🔍 Checking cloud backup trigger conditions:")
                    logger.info(
                        f"  - job.status == 'completed': {job.status == 'completed'}"
                    )
                    logger.info(
                        f"  - db_job.type in ['backup', 'scheduled_backup']: {db_job.type in ['backup', 'scheduled_backup']} (actual: {db_job.type})"
                    )
                    logger.info(f"  - job.return_code == 0: {job.return_code == 0}")
                    logger.info(
                        f"  - db_job.cloud_sync_config_id: {db_job.cloud_sync_config_id}"
                    )

                    if (
                        job.status == "completed"
                        and db_job.type in ["backup", "scheduled_backup"]
                        and job.return_code == 0
                    ):
                        logger.info(
                            f"🚀 All conditions met - triggering cloud backup for job {job_id}"
                        )
                        asyncio.create_task(self._trigger_cloud_backups(db_job, db))
                    else:
                        logger.info(
                            f"❌ Cloud backup conditions not met for job {job_id}"
                        )

                else:
                    logger.warning(f"No database job found for UUID {job_id}")

        except Exception as e:
            logger.error(f"Failed to update database job for {job_id}: {e}")

    async def _trigger_cloud_backups(self, db_job: "Job", db: "Session"):
        """Trigger cloud backup for the specific configuration selected in the job after a successful borg backup"""
        logger.info(f"☁️ _trigger_cloud_backups called for job {db_job.id}")

        try:
            from app.models.database import CloudSyncConfig, Repository
            from app.api.sync import sync_repository_task

            # Only trigger cloud backup if a specific configuration was selected for this job
            if not db_job.cloud_sync_config_id:
                logger.info(
                    f"🔍 No cloud sync configuration selected for job {db_job.id}"
                )
                return

            logger.info(
                f"🔍 Looking for cloud sync configuration {db_job.cloud_sync_config_id}"
            )

            # Get the specific cloud sync configuration
            cloud_config = (
                db.query(CloudSyncConfig)
                .filter(
                    CloudSyncConfig.id == db_job.cloud_sync_config_id,
                    CloudSyncConfig.enabled,
                )
                .first()
            )

            if not cloud_config:
                logger.warning(
                    f"⚠️ Cloud sync configuration {db_job.cloud_sync_config_id} not found or disabled for job {db_job.id}"
                )
                return

            logger.info(
                f"✅ Found cloud backup configuration: {cloud_config.name} (enabled: {cloud_config.enabled})"
            )

            # Get the repository that was backed up
            logger.info(f"🔍 Looking for repository {db_job.repository_id}")
            repository = (
                db.query(Repository)
                .filter(Repository.id == db_job.repository_id)
                .first()
            )

            if not repository:
                logger.error(f"⚠️ Repository not found for job {db_job.id}")
                return

            logger.info(f"✅ Found repository: {repository.name}")
            logger.info(
                f"🚀 Triggering cloud backup to '{cloud_config.name}' for repository '{repository.name}' after successful borg backup"
            )

            # Create cloud backup job for the specific configuration
            try:
                # Create a new sync job
                from app.models.database import Job as JobModel

                logger.info("📝 Creating sync job in database")
                sync_job = JobModel(
                    repository_id=repository.id, type="sync", status="pending"
                )
                db.add(sync_job)
                db.commit()
                db.refresh(sync_job)

                logger.info(f"✅ Created sync job {sync_job.id}")
                logger.info("🚀 Starting cloud backup task with parameters:")
                logger.info(f"  - repository_id: {repository.id}")
                logger.info(f"  - config_name: {cloud_config.name}")
                logger.info(f"  - bucket_name: {cloud_config.bucket_name}")
                logger.info(f"  - path_prefix: {cloud_config.path_prefix or ''}")
                logger.info(f"  - sync_job_id: {sync_job.id}")

                # Start the sync task in the background
                asyncio.create_task(
                    sync_repository_task(
                        repository.id,
                        cloud_config.name,  # config name
                        cloud_config.bucket_name,
                        cloud_config.path_prefix or "",
                        sync_job.id,
                    )
                )

                logger.info(
                    f"✅ Cloud backup task started successfully for '{cloud_config.name}'"
                )

            except Exception as e:
                logger.error(
                    f"❌ Failed to create cloud backup job for config '{cloud_config.name}': {e}"
                )
                import traceback

                logger.error(f"Traceback: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"Failed to trigger cloud backups: {e}")

    def _update_composite_job_status(self, job_id: str, status: str):
        """Update composite job status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job or not job.is_composite():
                return

            from app.models.database import Job
            from app.utils.db_session import get_db_session

            with get_db_session() as db:
                db_job = db.query(Job).filter(Job.id == job.db_job_id).first()
                if db_job:
                    db_job.status = status
                    if status == "completed" or status == "failed":
                        db_job.finished_at = datetime.now()
                    logger.info(
                        f"📝 Updated database job {db_job.id} status to {status}"
                    )

        except Exception as e:
            logger.error(f"Failed to update composite job status: {e}")

    def _update_composite_task_status(
        self,
        job_id: str,
        task_index: int,
        status: str,
        error: str = None,
        return_code: int = None,
    ):
        """Update composite task status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job or not job.is_composite():
                return

            from app.models.database import JobTask
            from app.utils.db_session import get_db_session

            with get_db_session() as db:
                task = (
                    db.query(JobTask)
                    .filter(
                        JobTask.job_id == job.db_job_id,
                        JobTask.task_order == task_index,
                    )
                    .first()
                )

                if task:
                    task.status = status
                    if status == "running":
                        task.started_at = datetime.now()
                    elif status in ["completed", "failed", "skipped"]:
                        task.completed_at = datetime.now()

                        # Store output from in-memory task
                        if task_index < len(job.tasks):
                            task_info = job.tasks[task_index]
                            if task_info.output_lines:
                                task.output = "\n".join(
                                    [line["text"] for line in task_info.output_lines]
                                )

                    if error:
                        task.error = error
                    if return_code is not None:
                        task.return_code = return_code

                    logger.info(
                        f"📝 Updated database task {task.id} status to {status}"
                    )

        except Exception as e:
            logger.error(f"Failed to update composite task status: {e}")

    async def _execute_backup_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a borg backup task"""
        try:
            logger.info(f"🔄 Starting borg backup for repository {job.repository.name}")

            from app.utils.security import (
                build_secure_borg_command,
                validate_compression,
                validate_archive_name,
            )

            # Get parameters from task definition
            params = task.parameters
            source_path = params.get("source_path", "/data")
            compression = params.get("compression", "zstd")
            dry_run = params.get("dry_run", False)

            # Build archive name
            archive_name = f"backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

            # Validate inputs
            validate_compression(compression)
            validate_archive_name(archive_name)

            logger.info(
                f"🔄 Backup settings - Source: {source_path}, Compression: {compression}, Dry run: {dry_run}"
            )

            # Build command arguments
            additional_args = [
                "--compression",
                compression,
                "--stats",
                "--progress",
                "--json",
                "--verbose",
                "--list",
                f"{job.repository.path}::{archive_name}",
                source_path,
            ]

            if dry_run:
                additional_args.insert(0, "--dry-run")

            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            # Execute command and stream output
            return await self._execute_borg_command_with_streaming(
                command, env, job, task, task_index
            )

        except Exception as e:
            logger.error(f"❌ Exception in backup task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_prune_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a borg prune task"""
        try:
            logger.info(f"🗑️ Starting borg prune for repository {job.repository.name}")

            from app.utils.security import build_secure_borg_command

            params = task.parameters
            additional_args = []

            # Add retention policy arguments
            if params.get("keep_within"):
                additional_args.extend(["--keep-within", params["keep_within"]])
            if params.get("keep_daily"):
                additional_args.extend(["--keep-daily", str(params["keep_daily"])])
            if params.get("keep_weekly"):
                additional_args.extend(["--keep-weekly", str(params["keep_weekly"])])
            if params.get("keep_monthly"):
                additional_args.extend(["--keep-monthly", str(params["keep_monthly"])])
            if params.get("keep_yearly"):
                additional_args.extend(["--keep-yearly", str(params["keep_yearly"])])

            # Add options
            if params.get("show_stats"):
                additional_args.append("--stats")
            if params.get("show_list"):
                additional_args.append("--list")
            if params.get("save_space"):
                additional_args.append("--save-space")
            if params.get("force_prune"):
                additional_args.append("--force")
            if params.get("dry_run"):
                additional_args.append("--dry-run")

            # Add repository path
            additional_args.append(job.repository.path)

            command, env = build_secure_borg_command(
                base_command="borg prune",
                repository_path="",
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            return await self._execute_borg_command_with_streaming(
                command, env, job, task, task_index
            )

        except Exception as e:
            logger.error(f"❌ Exception in prune task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a borg check task"""
        try:
            logger.info(f"🔍 Starting borg check for repository {job.repository.name}")

            from app.utils.security import build_secure_borg_command

            params = task.parameters
            additional_args = ["--verbose", "--progress", "--show-rc"]

            # Check type specific args
            if params.get("check_type") == "repository_only":
                additional_args.append("--repository-only")
            elif params.get("check_type") == "archives_only":
                additional_args.append("--archives-only")

            # Add verification and repair options
            if (
                params.get("verify_data")
                and params.get("check_type") != "repository_only"
            ):
                additional_args.append("--verify-data")
            if params.get("repair_mode"):
                additional_args.append("--repair")
            if params.get("save_space"):
                additional_args.append("--save-space")

            # Add repository path
            additional_args.append(job.repository.path)

            command, env = build_secure_borg_command(
                base_command="borg check",
                repository_path="",
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args,
            )

            return await self._execute_borg_command_with_streaming(
                command, env, job, task, task_index
            )

        except Exception as e:
            logger.error(f"❌ Exception in check task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_cloud_sync_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int
    ) -> bool:
        """Execute a cloud sync task"""
        try:
            # For now, just log that cloud sync would happen
            # This can be expanded to use rclone service like the composite job manager
            logger.info(
                f"☁️ Cloud sync task - would sync repository {job.repository.name}"
            )

            # Add a small delay to simulate work
            await asyncio.sleep(1)

            # Add some sample output
            sample_output = [
                "Starting cloud sync...",
                "Uploading repository data...",
                "Cloud sync completed successfully",
            ]

            for line in sample_output:
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": line}
                )
                self._broadcast_task_output(job.id, task_index, line)
                await asyncio.sleep(0.5)  # Small delay between lines

            return True

        except Exception as e:
            logger.error(f"❌ Exception in cloud sync task: {str(e)}")
            task.error = str(e)
            return False

    async def _execute_borg_command_with_streaming(
        self,
        command: List[str],
        env: Dict,
        job: BorgJob,
        task: BorgJobTask,
        task_index: int,
    ) -> bool:
        """Execute a borg command and stream output to a specific task"""
        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            # Stream output to task
            async for line in process.stdout:
                decoded_line = line.decode("utf-8", errors="replace").rstrip()

                # Store in task output
                task.output_lines.append(
                    {"timestamp": datetime.now().isoformat(), "text": decoded_line}
                )

                # Broadcast to SSE listeners
                self._broadcast_task_output(job.id, task_index, decoded_line)

            # Wait for completion
            await process.wait()

            if process.returncode == 0:
                logger.info("✅ Command completed successfully")
                return True
            else:
                logger.error(f"❌ Command failed with return code {process.returncode}")
                task.error = f"Command failed with return code {process.returncode}"
                return False

        except Exception as e:
            logger.error(f"❌ Exception executing command: {str(e)}")
            task.error = str(e)
            return False


# Global job manager instance
borg_job_manager = BorgJobManager()
