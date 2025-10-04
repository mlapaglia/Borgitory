"""
External Job Manager - Handles external job registration and management
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask
from borgitory.services.jobs.broadcaster.event_type import EventType

logger = logging.getLogger(__name__)


class ExternalJobManager:
    """Handles external job registration and management"""

    def __init__(
        self, jobs: Dict[str, BorgJob], output_manager: Any, event_broadcaster: Any
    ):
        self.jobs = jobs
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster

    def register_external_job(
        self, job_id: str, job_type: str = "backup", job_name: str = "External Backup"
    ) -> None:
        """
        Register an external job (from BackupService) for monitoring purposes.
        All jobs are now composite jobs with at least one task.

        Args:
            job_id: Unique job identifier
            job_type: Type of job (backup, prune, check, etc.)
            job_name: Human-readable job name
        """
        if job_id in self.jobs:
            logger.warning(f"Job {job_id} already registered, updating status")

        # Create the main task for this job
        main_task = BorgJobTask(
            task_type=job_type,
            task_name=job_name,
            status="running",
            started_at=now_utc(),
        )

        # Create a composite BorgJob (all jobs are now composite)
        job = BorgJob(
            id=job_id,
            command=[],  # External jobs don't have direct commands
            job_type="composite",  # All jobs are now composite
            status="running",
            started_at=now_utc(),
            repository_id=None,  # Can be set later if needed
            schedule=None,
            tasks=[main_task],  # Always has at least one task
        )

        self.jobs[job_id] = job

        # Initialize output tracking
        self.output_manager.create_job_output(job_id)

        # Broadcast job started event
        self.event_broadcaster.broadcast_event(
            EventType.JOB_STARTED,
            job_id=job_id,
            data={"job_type": job_type, "job_name": job_name, "external": True},
        )

        logger.info(
            f"Registered external composite job {job_id} ({job_type}) with 1 task for monitoring"
        )

    def update_external_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        return_code: Optional[int] = None,
    ) -> None:
        """
        Update the status of an external job and its main task.

        Args:
            job_id: Job identifier
            status: New status (running, completed, failed, etc.)
            error: Error message if failed
            return_code: Process return code
        """
        if job_id not in self.jobs:
            logger.warning(f"Cannot update external job {job_id} - not registered")
            return

        job = self.jobs[job_id]
        old_status = job.status
        job.status = status

        if error:
            job.error = error

        if return_code is not None:
            job.return_code = return_code

        if status in ["completed", "failed"]:
            job.completed_at = now_utc()

        # Update the main task status as well
        if job.tasks:
            main_task = job.tasks[0]  # First task is the main task
            main_task.status = status
            if error:
                main_task.error = error
            if return_code is not None:
                main_task.return_code = return_code
            if status in ["completed", "failed"]:
                main_task.completed_at = now_utc()

        # Broadcast status change event
        if old_status != status:
            if status == "completed":
                event_type = EventType.JOB_COMPLETED
            elif status == "failed":
                event_type = EventType.JOB_FAILED
            else:
                event_type = EventType.JOB_STATUS_CHANGED

            self.event_broadcaster.broadcast_event(
                event_type,
                job_id=job_id,
                data={"old_status": old_status, "new_status": status, "external": True},
            )

        logger.debug(
            f"Updated external job {job_id} and main task status: {old_status} -> {status}"
        )

    def add_external_job_output(self, job_id: str, output_line: str) -> None:
        """
        Add output line to an external job's main task.

        Args:
            job_id: Job identifier
            output_line: Output line to add
        """
        if job_id not in self.jobs:
            logger.warning(
                f"Cannot add output to external job {job_id} - not registered"
            )
            return

        job = self.jobs[job_id]

        # Add output to the main task
        if job.tasks:
            main_task = job.tasks[0]
            # Store output in dict format for backward compatibility
            main_task.output_lines.append({"text": output_line})

        # Also add output through output manager for streaming
        asyncio.create_task(self.output_manager.add_output_line(job_id, output_line))

        # Broadcast output event for real-time streaming
        self.event_broadcaster.broadcast_event(
            EventType.JOB_OUTPUT,
            job_id=job_id,
            data={
                "line": output_line,
                "task_index": 0,  # External jobs use main task (index 0)
                "progress": None,
            },
        )

    def unregister_external_job(self, job_id: str) -> None:
        """
        Unregister an external job (cleanup after completion).

        Args:
            job_id: Job identifier to unregister
        """
        if job_id in self.jobs:
            job = self.jobs[job_id]
            logger.info(
                f"Unregistering external job {job_id} (final status: {job.status})"
            )

            # Use existing cleanup method
            self._cleanup_job(job_id)
        else:
            logger.warning(f"Cannot unregister external job {job_id} - not found")

    def _cleanup_job(self, job_id: str) -> bool:
        """Clean up job resources"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            logger.debug(f"Cleaning up job {job_id} (status: {job.status})")

            del self.jobs[job_id]

            self.output_manager.clear_job_output(job_id)

            return True
        return False
