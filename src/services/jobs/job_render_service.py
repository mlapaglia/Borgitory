import logging
from typing import AsyncGenerator
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from models.database import Job
from models.enums import JobType
from services.jobs.job_manager import JobManager

logger = logging.getLogger(__name__)


class JobRenderService:
    """Service for rendering job-related HTML templates"""

    def __init__(
        self,
        job_manager: JobManager,
        templates_dir: str = "src/templates",
    ):
        self.templates = Jinja2Templates(directory=templates_dir)
        self.job_manager = job_manager

    def render_jobs_html(self, db: Session, expand: str = None) -> str:
        """Render job history as HTML"""
        try:
            # Get recent jobs (last 20) with their tasks
            db_jobs = (
                db.query(Job)
                .options(joinedload(Job.repository), joinedload(Job.tasks))
                .order_by(Job.started_at.desc())
                .limit(20)
                .all()
            )

            if not db_jobs:
                return self.templates.get_template(
                    "partials/jobs/empty_state.html"
                ).render(message="No job history available.", padding="8")

            html_content = '<div class="space-y-3">'

            for job in db_jobs:
                # Only render jobs that have UUIDs
                if not job.id:
                    continue

                should_expand = expand and job.id == expand
                html_content += self._render_job_html(job, expand_details=should_expand)

            html_content += "</div>"
            return html_content

        except Exception as e:
            logger.error(f"Error generating jobs HTML: {e}")
            return self.templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading jobs: {str(e)}", padding="4"
            )

    def render_current_jobs_html(self) -> str:
        """Render current running jobs as HTML"""
        try:
            current_jobs = []

            # Get current jobs from unified manager
            for job_id, job in self.job_manager.jobs.items():
                if job.status == "running":
                    # All jobs are composite now, check if they have tasks
                    if job.tasks:
                        # Handle composite job (like Manual Backup)
                        current_task = job.get_current_task()
                        progress_info = f"Task: {current_task.task_name if current_task else 'Unknown'} ({job.current_task_index + 1}/{len(job.tasks)})"

                        # Get display name from JobType enum
                        display_type = JobType.from_job_type_string(str(job.job_type))

                        current_jobs.append(
                            {
                                "id": job_id,
                                "type": display_type,
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
                    else:
                        # Handle simple borg job (only show if not part of a composite job)
                        # Skip jobs that are likely created by composite jobs
                        if not self._is_child_of_composite_job(job_id, job):
                            job_type = JobType.from_command(getattr(job, "command", []))

                            # Calculate progress info
                            progress_info = ""
                            if (
                                hasattr(job, "current_progress")
                                and job.current_progress
                            ):
                                if "files" in job.current_progress:
                                    progress_info = (
                                        f"Files: {job.current_progress['files']}"
                                    )
                                if "transferred" in job.current_progress:
                                    progress_info += (
                                        f" | {job.current_progress['transferred']}"
                                        if progress_info
                                        else job.current_progress["transferred"]
                                    )

                            current_jobs.append(
                                {
                                    "id": job_id,
                                    "type": job_type,
                                    "status": job.status,
                                    "started_at": job.started_at.strftime("%H:%M:%S"),
                                    "progress": getattr(job, "current_progress", None),
                                    "progress_info": progress_info,
                                }
                            )

            # Render using template
            return self.templates.get_template(
                "partials/jobs/current_jobs_list.html"
            ).render(
                current_jobs=current_jobs,
                message="No operations currently running.",
                padding="4",
            )

        except Exception as e:
            logger.error(f"Error loading current operations: {e}")
            return self.templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading current operations: {str(e)}", padding="4"
            )

    def _is_child_of_composite_job(self, job_id: str, job) -> bool:
        """Check if a job is a child task of a composite job"""
        # Simple heuristic: if there are composite jobs running,
        # assume simple borg jobs are their children
        for other_job_id, other_job in self.job_manager.jobs.items():
            if (
                other_job.tasks  # All jobs are composite now
                and other_job.status == "running"
                and other_job_id != job_id
            ):
                return True
        return False

    def _render_job_html(self, job: Job, expand_details: bool = False) -> str:
        """Render HTML for a single job (simple or composite)"""
        repository_name = job.repository.name if job.repository else "Unknown"

        # Only process jobs that have UUIDs - skip legacy jobs without UUIDs
        if not job.id:
            return ""  # Don't render jobs without UUIDs

        job_id = job.id

        # Status styling
        if job.status == "completed":
            status_class = "bg-green-100 text-green-800"
            status_icon = "✓"
        elif job.status == "failed":
            status_class = "bg-red-100 text-red-800"
            status_icon = "✗"
        elif job.status == "running":
            status_class = "bg-blue-100 text-blue-800"
            status_icon = "⟳"
        else:
            status_class = "bg-gray-100 text-gray-800"
            status_icon = "◦"

        # Format dates
        started_at = (
            job.started_at.strftime("%Y-%m-%d %H:%M") if job.started_at else "N/A"
        )
        finished_at = (
            job.finished_at.strftime("%Y-%m-%d %H:%M") if job.finished_at else "N/A"
        )

        # Debug logging
        logger.info(f"Job {job.id[:8]}...: has {len(job.tasks) if job.tasks else 0} tasks")
        if job.tasks:
            for i, task in enumerate(job.tasks):
                logger.info(f"  Task {i}: {task.task_name} ({task.task_type}) - {task.status}")

        # Job header
        job_title = f"{job.type.replace('_', ' ').title()} - {repository_name}"
        progress_text = f"({job.completed_tasks}/{job.total_tasks} tasks)"
        job_title += f" {progress_text}"

        # Sort tasks by order if composite
        sorted_tasks = (
            sorted(job.tasks, key=lambda t: t.task_order)
        )

        # Fix task statuses for failed jobs
        if job.status == "failed":
            sorted_tasks = self._fix_task_statuses_for_failed_job(sorted_tasks)

        # Create a job context object that uses UUID as the primary ID
        job_context = type(
            "JobContext",
            (),
            {
                "id": job_id,  # Use the UUID as the ID
                "status": job.status,
                "job_type": job.job_type,
                "type": job.type,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "error": job.error,
                "job_uuid": job.id,
            },
        )()

        # Render the template with context
        return self.templates.get_template("partials/jobs/job_item.html").render(
            job=job_context,
            repository_name=repository_name,
            status_class=status_class,
            status_icon=status_icon,
            started_at=started_at,
            finished_at=finished_at,
            job_title=job_title,
            sorted_tasks=sorted_tasks,
            expand_details=expand_details,
        )

    def get_job_for_render(self, job_id: str, db: Session) -> dict:
        """Get job data formatted for template rendering - prioritize database for completed jobs"""
        try:
            logger.info(f"Getting job {job_id} for rendering")

            # Always check database first for job data
            job = (
                db.query(Job)
                .options(joinedload(Job.repository), joinedload(Job.tasks))
                .filter(Job.id == job_id)
                .first()
            )

            # If job exists in database and is completed/failed, use database data exclusively
            if job and job.status in ["completed", "failed"]:
                logger.info(
                    f"Found completed/failed job {job_id} in database, using database data"
                )
                return self._format_database_job_for_render(job)

            # For running jobs or jobs not in database, check job manager
            if job_id in self.job_manager.jobs:
                logger.info(f"Found running job {job_id} in job manager")
                manager_job = self.job_manager.jobs[job_id]
                return self._format_manager_job_for_render(manager_job, job_id, job)

            # If job exists in database but not completed (edge case), still show it
            if job:
                logger.info(f"Found job {job_id} in database (status: {job.status})")
                return self._format_database_job_for_render(job)

            logger.info(f"Job {job_id} not found anywhere")
            return None
        except Exception as e:
            logger.error(f"Error getting job for render: {e}")
            return None

    def _format_database_job_for_render(self, job: Job) -> dict:
        """Format a database job for template rendering"""
        try:
            repository_name = job.repository.name if job.repository else "Unknown"

            # Status styling
            if job.status == "completed":
                status_class = "bg-green-100 text-green-800"
                status_icon = "✓"
            elif job.status == "failed":
                status_class = "bg-red-100 text-red-800"
                status_icon = "✗"
            elif job.status == "running":
                status_class = "bg-blue-100 text-blue-800"
                status_icon = "⟳"
            else:
                status_class = "bg-gray-100 text-gray-800"
                status_icon = "◦"

            # Format dates
            started_at = (
                job.started_at.strftime("%Y-%m-%d %H:%M") if job.started_at else "N/A"
            )
            finished_at = (
                job.finished_at.strftime("%Y-%m-%d %H:%M") if job.finished_at else "N/A"
            )

            # All jobs are now composite with tasks
            has_tasks = bool(job.tasks and len(job.tasks) > 0)

            # Debug logging
            logger.info(f"Job {job.id[:8]}...: has {len(job.tasks) if job.tasks else 0} tasks")
            if job.tasks:
                for i, task in enumerate(job.tasks):
                    logger.info(f"  Task {i}: {task.task_name} ({task.task_type}) - {task.status}")

            # Job header
            job_title = f"{job.type.replace('_', ' ').title()} - {repository_name}"
            if has_tasks:
                progress_text = (
                    f"({job.completed_tasks or 0}/{job.total_tasks or 0} tasks)"
                )
                job_title += f" {progress_text}"

            # Sort tasks by order (all jobs have tasks now)
            sorted_tasks = (
                sorted(job.tasks, key=lambda t: t.task_order) if has_tasks else []
            )

            # Fix task statuses for failed jobs
            if has_tasks and job.status == "failed":
                sorted_tasks = self._fix_task_statuses_for_failed_job(sorted_tasks)

            # Create a job context object that uses UUID as the primary ID
            job_context = type(
                "JobContext",
                (),
                {
                    "id": job.id,  # Use the UUID as the ID
                    "status": job.status,
                    "job_type": job.job_type,
                    "type": job.type,
                    "started_at": job.started_at,
                    "finished_at": job.finished_at,
                    "error": job.error,
                    "job_uuid": job.id,
                },
            )()

            return {
                "job": job_context,
                "repository_name": repository_name,
                "status_class": status_class,
                "status_icon": status_icon,
                "started_at": started_at,
                "finished_at": finished_at,
                "job_title": job_title,
                "sorted_tasks": sorted_tasks,
            }
        except Exception as e:
            logger.error(f"Error formatting database job {job.id}: {e}")
            return None

    def _format_manager_job_for_render(self, manager_job, job_id, db_job=None):
        """Format a job manager job for template rendering"""
        try:
            # Use database job data if available, otherwise create from manager job
            if db_job:
                repository_name = (
                    db_job.repository.name if db_job.repository else "Unknown"
                )
                job_type = db_job.type
                # Prioritize database status for completed/failed jobs to ensure consistency
                if db_job.status in ["completed", "failed"]:
                    job_status = db_job.status
                else:
                    job_status = (
                        manager_job.status
                    )  # Use manager status for running jobs
            else:
                # Extract info from manager job (this may need adjustment based on your job structure)
                repository_name = getattr(manager_job, "repository_name", "Unknown")
                job_type = getattr(manager_job, "job_type", "composite")
                job_status = manager_job.status

            # Status styling
            if job_status == "completed":
                status_class = "bg-green-100 text-green-800"
                status_icon = "✓"
            elif job_status == "failed":
                status_class = "bg-red-100 text-red-800"
                status_icon = "✗"
            elif job_status == "running":
                status_class = "bg-blue-100 text-blue-800"
                status_icon = "⟳"
            else:
                status_class = "bg-gray-100 text-gray-800"
                status_icon = "◦"

            # Format dates
            started_at = (
                manager_job.started_at.strftime("%Y-%m-%d %H:%M")
                if manager_job.started_at
                else "N/A"
            )
            finished_at = (
                manager_job.completed_at.strftime("%Y-%m-%d %H:%M")
                if hasattr(manager_job, "completed_at") and manager_job.completed_at
                else "N/A"
            )

            # All jobs are now composite - check if they have tasks
            has_tasks = hasattr(manager_job, "tasks") and manager_job.tasks and len(manager_job.tasks) > 0

            # Job title
            job_title = f"{job_type.replace('_', ' ').title()} - {repository_name}"
            if has_tasks:
                # Use appropriate task count based on data source
                if db_job and db_job.status in ["completed", "failed"]:
                    # Use database task counts for completed/failed jobs
                    completed_tasks = db_job.completed_tasks or 0
                    total_tasks = db_job.total_tasks or 0
                elif hasattr(manager_job, "tasks"):
                    # Use manager task counts for running jobs
                    completed_tasks = sum(
                        1 for task in manager_job.tasks if task.status == "completed"
                    )
                    total_tasks = len(manager_job.tasks)
                else:
                    completed_tasks = 0
                    total_tasks = 0

                if total_tasks > 0:
                    progress_text = f"({completed_tasks}/{total_tasks} tasks)"
                    job_title += f" {progress_text}"

            # Convert manager job tasks to format expected by templates
            sorted_tasks = []
            if has_tasks:
                # If we're using database status for completed/failed jobs, use database tasks too
                if db_job and db_job.status in ["completed", "failed"] and db_job.tasks:
                    # Use database tasks for consistency
                    sorted_tasks = sorted(db_job.tasks, key=lambda t: t.task_order)
                elif hasattr(manager_job, "tasks"):
                    # Use manager tasks for running jobs
                    for i, task in enumerate(manager_job.tasks):
                        # Ensure task has task_order property for templates
                        if not hasattr(task, "task_order"):
                            task.task_order = i

                        # Convert output_lines to output string for templates
                        if hasattr(task, "output_lines") and task.output_lines:
                            task.output = "\n".join(
                                [
                                    line.get("text", "")
                                    if isinstance(line, dict)
                                    else str(line)
                                    for line in task.output_lines
                                ]
                            )
                        else:
                            task.output = ""

                        sorted_tasks.append(task)

            # Create a job context object that uses UUID as the primary ID
            job_context = type(
                "JobContext",
                (),
                {
                    "id": job_id,  # Use the UUID as the ID
                    "status": job_status,
                    "job_type": job_type,
                    "type": job_type,
                    "started_at": manager_job.started_at,
                    "finished_at": getattr(manager_job, "completed_at", None),
                    "error": getattr(manager_job, "error", None),
                    "job_uuid": job_id,
                },
            )()

            return {
                "job": job_context,  # Use the context object with UUID as ID
                "job_title": job_title,
                "status_class": status_class,
                "status_icon": status_icon,
                "started_at": started_at,
                "finished_at": finished_at if job_status != "running" else None,
                "repository_name": repository_name,
                "sorted_tasks": sorted_tasks,
                "expand_details": False,  # Will be set by the caller
            }
        except Exception as e:
            logger.error(f"Error formatting manager job {job_id}: {e}")
            return None

    def _fix_task_statuses_for_failed_job(self, sorted_tasks):
        """
        Fix task statuses for failed jobs to ensure proper display.

        When a job fails:
        - Tasks before the failed task should be 'completed'
        - The task that caused failure should be 'failed'
        - Tasks after the failed task should be 'skipped'
        """
        if not sorted_tasks:
            return sorted_tasks

        # Find the first failed task or the first running task (which likely failed)
        failed_task_index = None
        for i, task in enumerate(sorted_tasks):
            if task.status == "failed":
                failed_task_index = i
                break
            elif task.status == "running":
                # If a task is still showing as running but the job failed,
                # this task likely failed but wasn't updated properly
                failed_task_index = i
                # Update the status to failed for display purposes
                task.status = "failed"
                break

        if failed_task_index is not None:
            # Mark all tasks after the failed task as skipped
            for i in range(failed_task_index + 1, len(sorted_tasks)):
                task = sorted_tasks[i]
                if task.status in ["pending", "running"]:
                    task.status = "skipped"

        # Also handle the case where no explicit failed task is found
        # but there are still running tasks in a failed job
        else:
            # Mark all running/pending tasks as failed (conservative approach)
            for task in sorted_tasks:
                if task.status in ["running", "pending"]:
                    task.status = "failed"

        return sorted_tasks

    async def stream_current_jobs_html(self) -> "AsyncGenerator[str, None]":
        """Stream current jobs as HTML via Server-Sent Events"""

        try:
            # Send initial HTML
            initial_html = self.render_current_jobs_html()
            yield f"data: {initial_html}\n\n"

            # Subscribe to job events for real-time updates
            async for event in self.job_manager.stream_all_job_updates():
                try:
                    # Re-render current jobs HTML when events occur
                    updated_html = self.render_current_jobs_html()
                    yield f"data: {updated_html}\n\n"
                except Exception as e:
                    logger.error(f"Error generating HTML update: {e}")
                    # Send error state
                    error_html = self.templates.get_template(
                        "partials/jobs/error_state.html"
                    ).render(message="Error updating job status", padding="4")
                    yield f"data: {error_html}\n\n"

        except Exception as e:
            logger.error(f"Error in HTML job stream: {e}")
            error_html = self.templates.get_template(
                "partials/jobs/error_state.html"
            ).render(message=f"Error streaming jobs: {str(e)}", padding="4")
            yield f"data: {error_html}\n\n"
