from enum import Enum


class EventType(Enum):
    """Types of job events"""

    JOB_STARTED = "job_started"
    JOB_PROGRESS = "job_progress"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    JOB_STATUS_CHANGED = "job_status_changed"
    JOB_OUTPUT = "job_output"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    JOBS_UPDATE = "jobs_update"
    QUEUE_UPDATE = "queue_update"
    KEEPALIVE = "keepalive"
