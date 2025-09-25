"""
Protocol interfaces for job management services.
"""

from typing import Protocol, Dict, List, Optional, AsyncGenerator, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, field
import asyncio
from borgitory.custom_types import ConfigDict


@dataclass
class TaskDefinition:
    """Definition for a task in a composite job."""

    type: str  # Task type: 'backup', 'prune', 'check', 'cloud_sync', 'hook', 'notification'
    name: str  # Human-readable task name

    # Additional parameters specific to the task type
    parameters: ConfigDict = field(default_factory=dict)

    # Optional scheduling/execution parameters
    priority: Optional[int] = None
    timeout: Optional[int] = None
    retry_count: Optional[int] = None


if TYPE_CHECKING:
    from borgitory.services.jobs.job_manager import BorgJob
    from borgitory.services.jobs.broadcaster.job_event import JobEvent
    from borgitory.models.database import Repository, Schedule
    from borgitory.services.debug_service import DebugInfo, SystemInfo, JobManagerInfo
    from borgitory.services.volumes.volume_service import VolumeInfo
    from sqlalchemy.orm import Session


class JobStatusProtocol(Protocol):
    """Protocol for job status information."""

    @property
    def id(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...


class JobManagerProtocol(Protocol):
    """Protocol for job management services."""

    # Properties
    @property
    def jobs(self) -> Dict[str, "BorgJob"]:
        """Dictionary of active jobs."""
        ...

    # Core job methods
    def list_jobs(self) -> Dict[str, "BorgJob"]:
        """Get dictionary of all jobs."""
        ...

    def get_job_status(self, job_id: str) -> Optional[Dict[str, object]]:
        """Get status of a specific job."""
        ...

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        ...

    # Event and streaming methods
    def subscribe_to_events(self) -> Optional[asyncio.Queue["JobEvent"]]:
        """Subscribe to job events."""
        ...

    def unsubscribe_from_events(self, client_queue: asyncio.Queue["JobEvent"]) -> bool:
        """Unsubscribe from job events."""
        ...

    def stream_job_output(self, job_id: str) -> AsyncGenerator[Dict[str, object], None]:
        """Stream output for a specific job."""
        ...

    def stream_all_job_updates(self) -> AsyncGenerator[object, None]:
        """Stream real-time job updates."""
        ...

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict[str, object]:
        """Get job output stream."""
        ...

    async def start_borg_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        is_backup: bool = False,
    ) -> str:
        """Start a borg command and return job ID."""
        ...

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up a completed job."""
        ...

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List[TaskDefinition],
        repository: "Repository",
        schedule: Optional["Schedule"] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a composite job with multiple tasks."""
        ...

    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        ...

    # Internal attributes that JobService accesses
    @property
    def _processes(self) -> Dict[str, "asyncio.subprocess.Process"]:
        """Internal processes dictionary."""
        ...


class JobStreamServiceProtocol(Protocol):
    """Protocol for job output streaming services."""

    async def stream_job_output(self, job_id: str) -> AsyncGenerator[str, None]: ...
    async def stream_all_job_updates(
        self,
    ) -> AsyncGenerator[Dict[str, object], None]: ...


class JobRenderServiceProtocol(Protocol):
    """Protocol for job rendering services."""

    async def render_jobs_html(self) -> str: ...
    async def stream_current_jobs_html(self) -> AsyncGenerator[str, None]: ...
    def get_jobs_for_display(self) -> List[Dict[str, object]]: ...


class DebugServiceProtocol(Protocol):
    """Protocol for debug/diagnostics services."""

    async def get_debug_info(self, db: "Session") -> "DebugInfo": ...
    async def _get_system_info(self) -> "SystemInfo": ...
    async def _get_volume_info(self) -> "VolumeInfo": ...
    def _get_job_manager_info(self) -> "JobManagerInfo": ...
