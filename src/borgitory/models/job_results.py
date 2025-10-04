"""
Typed result classes for Job Service operations.

This module replaces complex Dict[str, object] return types with proper dataclasses
for better type safety, IDE support, and code maintainability.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Union


class JobStatusEnum(str, Enum):
    """Job status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"
    QUEUED = "queued"


class JobTypeEnum(str, Enum):
    """Job type enumeration"""

    BACKUP = "backup"
    PRUNE = "prune"
    CHECK = "check"
    COMPOSITE = "composite"


@dataclass
class JobCreationResult:
    """Result of creating a new job"""

    job_id: str
    status: str = "started"


@dataclass
class JobCreationError:
    """Error result when job creation fails"""

    error: str
    error_code: Optional[str] = None


# Union type for job creation results
JobCreationResponse = Union[JobCreationResult, JobCreationError]


@dataclass
class JobStatus:
    """Comprehensive job status information"""

    id: str
    status: JobStatusEnum
    job_type: JobTypeEnum
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    current_task_index: Optional[int] = None
    total_tasks: int = 0

    # Computed properties for backward compatibility
    @property
    def running(self) -> bool:
        return self.status == JobStatusEnum.RUNNING

    @property
    def completed(self) -> bool:
        return self.status == JobStatusEnum.COMPLETED

    @property
    def failed(self) -> bool:
        return self.status == JobStatusEnum.FAILED


@dataclass
class JobStatusError:
    """Error when job status cannot be retrieved"""

    error: str
    job_id: Optional[str] = None


# Union type for job status results
JobStatusResponse = Union[JobStatus, JobStatusError]


@dataclass
class CompositeJobOutput:
    """Output information for composite jobs"""

    job_id: str
    job_type: str
    status: JobStatusEnum
    current_task_index: int
    total_tasks: int
    current_task_output: List[str]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class RegularJobOutput:
    """Output information for regular (non-composite) jobs"""

    job_id: str
    lines: List[str]
    total_lines: int
    has_more: bool = False
    last_updated: Optional[datetime] = None


# Union type for job output results
JobOutputResponse = Union[CompositeJobOutput, RegularJobOutput]


@dataclass
class ManagerStats:
    """Job manager statistics"""

    total_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_processes: int
    running_job_ids: List[str] = field(default_factory=list)


@dataclass
class QueueStats:
    """Queue statistics"""

    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0


@dataclass
class JobStopResult:
    """Result of stopping a job"""

    job_id: str
    success: bool
    message: str
    tasks_skipped: int = 0
    current_task_killed: bool = False


@dataclass
class JobStopError:
    """Error when stopping a job fails"""

    job_id: str
    error: str
    error_code: Optional[str] = None


# Union type for job stop results
JobStopResponse = Union[JobStopResult, JobStopError]
