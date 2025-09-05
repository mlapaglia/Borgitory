import logging
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from app.models.database import Job
from app.models.enums import JobType
from app.services.job_manager import borg_job_manager

logger = logging.getLogger(__name__)


class JobRenderService:
    """Service for rendering job-related HTML templates"""

    def __init__(self, templates_dir: str = "app/templates", job_manager=None):
        self.templates = Jinja2Templates(directory=templates_dir)
        self.job_manager = job_manager or borg_job_manager

    def render_jobs_html(self, db: Session, expand: str = None) -> str:
        """Render job history as HTML"""
        try:
            # Get recent jobs (last 20) with their tasks
            db_jobs = (
                db.query(Job)
                .options(joinedload(Job.repository), joinedload(Job.tasks))
                .order_by(Job.id.desc())
                .limit(20)
                .all()
            )

            if not db_jobs:
                return self.templates.get_template(
                    "partials/jobs/empty_state.html"
                ).render(message="No job history available.", padding="8")

            html_content = '<div class="space-y-3">'

            for job in db_jobs:
                should_expand = expand and (
                    str(job.id) == expand
                    or (job.job_uuid and job.job_uuid.startswith(expand[:8]))
                )
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
                    # Check if this is a composite job
                    if hasattr(job, "is_composite") and job.is_composite():
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
                hasattr(other_job, "is_composite")
                and other_job.is_composite()
                and other_job.status == "running"
                and other_job_id != job_id
            ):
                return True
        return False

    def _render_job_html(self, job: Job, expand_details: bool = False) -> str:
        """Render HTML for a single job (simple or composite)"""
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

        # Check if this is a composite job
        is_composite = job.job_type == "composite" and job.tasks

        # Job header
        job_title = f"{job.type.replace('_', ' ').title()} - {repository_name}"
        if is_composite:
            progress_text = f"({job.completed_tasks}/{job.total_tasks} tasks)"
            job_title += f" {progress_text}"

        # Sort tasks by order if composite
        sorted_tasks = (
            sorted(job.tasks, key=lambda t: t.task_order) if is_composite else []
        )

        # Render the template with context
        return self.templates.get_template("partials/jobs/job_item.html").render(
            job=job,
            repository_name=repository_name,
            status_class=status_class,
            status_icon=status_icon,
            started_at=started_at,
            finished_at=finished_at,
            job_title=job_title,
            is_composite=is_composite,
            sorted_tasks=sorted_tasks,
            expand_details=expand_details,
        )


# Global instance for dependency injection
job_render_service = JobRenderService()
