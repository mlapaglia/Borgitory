import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator, List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from borgitory.models.database import Job
from borgitory.protocols import JobManagerProtocol
from borgitory.services.jobs.job_manager import BorgJob

logger = logging.getLogger(__name__)


class JobStatusType(Enum):
    """Job status types for display"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class JobStatus:
    """Job status with display formatting"""

    type: JobStatusType
    css_class: str
    icon: str

    @classmethod
    def from_status_string(cls, status: str) -> "JobStatus":
        """Create JobStatus from string"""
        status_lower = status.lower()
        if status_lower == "completed":
            return cls(JobStatusType.COMPLETED, "bg-green-100 text-green-800", "✓")
        elif status_lower == "failed":
            return cls(JobStatusType.FAILED, "bg-red-100 text-red-800", "✗")
        elif status_lower == "running":
            return cls(JobStatusType.RUNNING, "bg-blue-100 text-blue-800", "⟳")
        elif status_lower == "pending":
            return cls(JobStatusType.PENDING, "bg-yellow-100 text-yellow-800", "◦")
        elif status_lower == "skipped":
            return cls(JobStatusType.CANCELLED, "bg-gray-100 text-gray-600", "⊘")
        else:
            return cls(JobStatusType.UNKNOWN, "bg-gray-100 text-gray-800", "?")


@dataclass
class TaskDisplayData:
    """Display data for a single task"""

    name: str
    type: str
    status: JobStatus
    output: str
    error: Optional[str]
    order: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    return_code: Optional[int]


@dataclass
class JobProgress:
    """Job progress information"""

    completed_tasks: int
    total_tasks: int
    current_task_name: Optional[str] = None

    @property
    def percentage(self) -> float:
        """Calculate completion percentage"""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    @property
    def display_text(self) -> str:
        """Get display text for progress"""
        return f"({self.completed_tasks}/{self.total_tasks} tasks)"


@dataclass
class JobDisplayData:
    """Complete display data for a job"""

    id: str
    title: str
    status: JobStatus
    repository_name: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    tasks: List[TaskDisplayData]
    progress: JobProgress
    error: Optional[str] = None

    @property
    def started_at_formatted(self) -> str:
        """Format start time for display"""
        return self.started_at.strftime("%Y-%m-%d %H:%M") if self.started_at else "N/A"

    @property
    def finished_at_formatted(self) -> str:
        """Format finish time for display"""
        return (
            self.finished_at.strftime("%Y-%m-%d %H:%M") if self.finished_at else "N/A"
        )


@dataclass
class TemplateTaskData:
    """Template-compatible task data structure"""

    task_name: str
    task_type: str
    status: str  # String for template conditionals
    output: str
    error: Optional[str]
    task_order: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    return_code: Optional[int]

    # Computed properties for templates
    @property
    def started_at_formatted(self) -> str:
        return self.started_at.strftime("%H:%M:%S") if self.started_at else "N/A"

    @property
    def completed_at_formatted(self) -> str:
        return self.completed_at.strftime("%H:%M:%S") if self.completed_at else "N/A"


class TemplateJobStatus:
    """Status object for template compatibility with {{ job.status.title() }}"""

    def __init__(self, status: str):
        self._status = status

    def title(self) -> str:
        return self._status.title()

    def __str__(self) -> str:
        return self._status


@dataclass
class TemplateJobContext:
    """Job context object for templates - mimics the old dynamic job context"""

    id: str
    status: TemplateJobStatus
    finished_at: Optional[datetime]
    error: Optional[str]


@dataclass
class TemplateJobData:
    """Template-compatible job data structure"""

    # Job context object (for job.* access in templates)
    job: TemplateJobContext

    # Root-level template variables
    job_title: str
    status_class: str
    status_icon: str
    started_at: str  # Pre-formatted
    finished_at: str  # Pre-formatted (not finished_at_formatted)
    repository_name: str
    sorted_tasks: List[TemplateTaskData]
    expand_details: bool = False  # For API state management


def convert_to_template_data(
    job_data: JobDisplayData, expand_details: bool = False
) -> TemplateJobData:
    """Convert JobDisplayData to template-compatible format"""
    # Convert tasks to template format
    template_tasks = []
    for task in job_data.tasks:
        template_task = TemplateTaskData(
            task_name=task.name,
            task_type=task.type,
            status=task.status.type.value,  # Convert enum to string
            output=task.output,
            error=task.error,
            task_order=task.order,
            started_at=task.started_at,
            completed_at=task.completed_at,
            return_code=task.return_code,
        )
        template_tasks.append(template_task)

    # Create job context object for template access
    job_context = TemplateJobContext(
        id=job_data.id,
        status=TemplateJobStatus(
            job_data.status.type.value
        ),  # Wrapper for .title() method
        finished_at=job_data.finished_at,
        error=job_data.error,
    )

    return TemplateJobData(
        job=job_context,
        job_title=job_data.title,
        status_class=job_data.status.css_class,
        status_icon=job_data.status.icon,
        started_at=job_data.started_at_formatted,
        finished_at=job_data.finished_at_formatted,
        repository_name=job_data.repository_name,
        sorted_tasks=template_tasks,
        expand_details=expand_details,
    )


class JobDataConverter:
    """Utility class for converting jobs to display data"""

    @staticmethod
    def convert_database_job(db_job: Job) -> JobDisplayData:
        """Convert database job to display data"""
        status = JobStatus.from_status_string(db_job.status)
        repository_name = db_job.repository.name if db_job.repository else "Unknown"

        # Convert tasks
        tasks = []
        if db_job.tasks:
            sorted_db_tasks = sorted(db_job.tasks, key=lambda t: t.task_order)
            for task in sorted_db_tasks:
                task_status = JobStatus.from_status_string(task.status)
                task_data = TaskDisplayData(
                    name=task.task_name,
                    type=task.task_type,
                    status=task_status,
                    output=task.output or "",
                    error=task.error,
                    order=task.task_order,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                    return_code=task.return_code,
                )
                tasks.append(task_data)

        # Calculate progress
        completed_tasks = db_job.completed_tasks or 0
        total_tasks = db_job.total_tasks or len(tasks)
        progress = JobProgress(completed_tasks, total_tasks)

        # Create title
        job_type_display = db_job.type.replace("_", " ").title()
        title = f"{job_type_display} - {repository_name}"
        if total_tasks > 0:
            title += f" {progress.display_text}"

        return JobDisplayData(
            id=db_job.id,
            title=title,
            status=status,
            repository_name=repository_name,
            started_at=db_job.started_at,
            finished_at=db_job.finished_at,
            tasks=tasks,
            progress=progress,
            error=db_job.error,
        )

    @staticmethod
    def convert_memory_job(
        memory_job: BorgJob, db_job: Optional[Job] = None
    ) -> JobDisplayData:
        """Convert in-memory job to display data"""
        status = JobStatus.from_status_string(memory_job.status)

        # Get repository name from database job if available
        if db_job and db_job.repository:
            repository_name = db_job.repository.name
        else:
            repository_name = getattr(memory_job, "repository_name", "Unknown")

        # Convert tasks
        tasks = []
        if hasattr(memory_job, "tasks") and memory_job.tasks:
            for i, task in enumerate(memory_job.tasks):
                task_status = JobStatus.from_status_string(task.status)

                # Convert output_lines to string
                output = ""
                if hasattr(task, "output_lines") and task.output_lines:
                    output = "\n".join(
                        [
                            line.get("text", "")
                            if isinstance(line, dict)
                            else str(line)
                            for line in task.output_lines
                        ]
                    )

                task_data = TaskDisplayData(
                    name=task.task_name,
                    type=task.task_type,
                    status=task_status,
                    output=output,
                    error=getattr(task, "error", None),
                    order=i,
                    started_at=getattr(task, "started_at", None),
                    completed_at=getattr(task, "completed_at", None),
                    return_code=getattr(task, "return_code", None),
                )
                tasks.append(task_data)

        # Calculate progress
        completed_tasks = sum(
            1 for task in tasks if task.status.type == JobStatusType.COMPLETED
        )
        total_tasks = len(tasks)
        current_task_name = None

        if memory_job.status == "running" and hasattr(memory_job, "current_task_index"):
            current_task = memory_job.get_current_task()
            if current_task:
                current_task_name = current_task.task_name

        progress = JobProgress(completed_tasks, total_tasks, current_task_name)

        # Create title
        job_type = getattr(memory_job, "job_type", "composite")
        job_type_display = job_type.replace("_", " ").title()
        title = f"{job_type_display} - {repository_name}"
        if total_tasks > 0:
            title += f" {progress.display_text}"

        return JobDisplayData(
            id=memory_job.id,
            title=title,
            status=status,
            repository_name=repository_name,
            started_at=memory_job.started_at,
            finished_at=getattr(memory_job, "completed_at", None),
            tasks=tasks,
            progress=progress,
            error=getattr(memory_job, "error", None),
        )

    @staticmethod
    def fix_failed_job_tasks(job_data: JobDisplayData) -> JobDisplayData:
        """Fix task statuses for failed jobs to ensure proper display"""
        if job_data.status.type != JobStatusType.FAILED or not job_data.tasks:
            return job_data

        # Find the first failed task
        failed_task_index = None
        for i, task in enumerate(job_data.tasks):
            if task.status.type == JobStatusType.FAILED:
                failed_task_index = i
                break
            elif task.status.type == JobStatusType.RUNNING:
                # Running task in failed job should be marked as failed
                task.status = JobStatus.from_status_string("failed")
                failed_task_index = i
                break

        # Mark subsequent tasks as skipped
        if failed_task_index is not None:
            for i in range(failed_task_index + 1, len(job_data.tasks)):
                task = job_data.tasks[i]
                if task.status.type in [JobStatusType.PENDING, JobStatusType.RUNNING]:
                    task.status = JobStatus.from_status_string("skipped")

        return job_data


class JobRenderService:
    """Service for rendering job-related HTML templates"""

    def __init__(
        self,
        job_manager: JobManagerProtocol,
        templates: Jinja2Templates,
        converter: Optional[JobDataConverter] = None,
    ) -> None:
        self.job_manager = job_manager
        self.templates = templates
        self.converter = converter or JobDataConverter()

    def get_job_display_data(
        self, job_id: str, db: Session
    ) -> Optional[JobDisplayData]:
        """Get job display data using simplified resolution strategy"""
        try:
            logger.info(f"Getting job {job_id} for display")

            # 1. Try database first (authoritative for completed jobs)
            db_job = (
                db.query(Job)
                .options(joinedload(Job.repository), joinedload(Job.tasks))
                .filter(Job.id == job_id)
                .first()
            )

            if db_job and db_job.status in ["completed", "failed"]:
                logger.info(f"Using database data for completed/failed job {job_id}")
                job_data = self.converter.convert_database_job(db_job)
                return self.converter.fix_failed_job_tasks(job_data)

            # 2. Try in-memory for running jobs
            logger.debug(f"Checking job manager for job {job_id}")
            logger.debug(
                f"Available jobs in manager: {list(self.job_manager.jobs.keys())}"
            )

            if job_id in self.job_manager.jobs:
                logger.info(f"Using in-memory data for running job {job_id}")
                memory_job = self.job_manager.jobs[job_id]
                job_data = self.converter.convert_memory_job(memory_job, db_job)
                return self.converter.fix_failed_job_tasks(job_data)
            else:
                logger.warning(
                    f"Job {job_id} not found in job manager (has {len(self.job_manager.jobs)} jobs)"
                )

            # 3. Fallback to database if exists
            if db_job:
                logger.info(
                    f"Using database data as fallback for job {job_id} (status: {db_job.status})"
                )
                job_data = self.converter.convert_database_job(db_job)
                return self.converter.fix_failed_job_tasks(job_data)

            logger.info(f"Job {job_id} not found")
            return None

        except Exception as e:
            logger.error(f"Error getting job display data for {job_id}: {e}")
            return None

    def render_jobs_html(self, db: Session, expand: str = "") -> str:
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

            for db_job in db_jobs:
                job_data = self.converter.convert_database_job(db_job)
                job_data = self.converter.fix_failed_job_tasks(job_data)
                should_expand = bool(expand and job_data.id == expand)
                html_content += self._render_job_html(
                    job_data, expand_details=should_expand
                )

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
            current_jobs_data = []

            # Get current running jobs from job manager
            for job_id, memory_job in self.job_manager.jobs.items():
                if memory_job.status == "running":
                    job_data = self.converter.convert_memory_job(memory_job)
                    current_jobs_data.append(
                        {
                            "id": job_data.id,
                            "type": job_data.title.split(" - ")[
                                0
                            ],  # Extract job type from title
                            "status": job_data.status.type.value,
                            "started_at": job_data.started_at.strftime("%H:%M:%S")
                            if job_data.started_at
                            else "N/A",
                            "progress_info": job_data.progress.current_task_name
                            or f"{job_data.progress.display_text}",
                        }
                    )

            # Render using template
            return self.templates.get_template(
                "partials/jobs/current_jobs_list.html"
            ).render(
                current_jobs=current_jobs_data,
                message="No operations currently running.",
                padding="4",
            )

        except Exception as e:
            logger.error(f"Error loading current operations: {e}")
            return self.templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading current operations: {str(e)}", padding="4"
            )

    def _render_job_html(
        self, job_data: JobDisplayData, expand_details: bool = False
    ) -> str:
        """Render HTML for a single job using JobDisplayData"""
        try:
            template_data = convert_to_template_data(job_data, expand_details)
            return self.templates.get_template("partials/jobs/job_item.html").render(
                template_data.__dict__
            )
        except Exception as e:
            logger.error(f"Error rendering job HTML for {job_data.id}: {e}")
            return f'<div class="error">Error rendering job {job_data.id}</div>'

    async def stream_current_jobs_html(self) -> AsyncGenerator[str, None]:
        """Stream current jobs as HTML via Server-Sent Events"""
        try:
            # Send initial HTML
            initial_html = self.render_current_jobs_html()
            for line in initial_html.splitlines():
                yield f"data: {line}\n"
            yield "data: \n\n"

            # Subscribe to job events for real-time updates
            async for event in self.job_manager.stream_all_job_updates():
                try:
                    # Re-render current jobs HTML when events occur
                    updated_html = self.render_current_jobs_html()
                    for line in updated_html.splitlines():
                        yield f"data: {line}\n"
                    yield "data: \n\n"
                except Exception as e:
                    logger.error(f"Error generating HTML update: {e}")
                    # Send error state
                    error_html = self.templates.get_template(
                        "partials/jobs/error_state.html"
                    ).render(message="Error updating job status", padding="4")
                    for line in error_html.splitlines():
                        yield f"data: {line}\n"
                    yield "data: \n\n"

        except Exception as e:
            logger.error(f"Error in HTML job stream: {e}")
            error_html = self.templates.get_template(
                "partials/jobs/error_state.html"
            ).render(message=f"Error streaming jobs: {str(e)}", padding="4")
            for line in error_html.splitlines():
                yield f"data: {line}\n"
            yield "data: \n\n"

    def get_job_for_template(
        self, job_id: str, db: Session, expand_details: bool = False
    ) -> Optional[TemplateJobData]:
        """Get job data formatted for template rendering"""
        job_data = self.get_job_display_data(job_id, db)
        if not job_data:
            return None
        return convert_to_template_data(job_data, expand_details)
