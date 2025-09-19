"""
Protocol interfaces for job management services.
"""

from typing import Protocol, Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime
import asyncio


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
    def jobs(self) -> Dict[str, Any]:
        """Dictionary of active jobs."""
        ...

    # Core job methods
    def list_jobs(self) -> Dict[str, Any]:
        """Get dictionary of all jobs."""
        ...

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        ...

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        ...

    # Event and streaming methods
    def subscribe_to_events(self) -> Optional[asyncio.Queue[Any]]:
        """Subscribe to job events."""
        ...

    def unsubscribe_from_events(self, client_queue: asyncio.Queue[Any]) -> bool:
        """Unsubscribe from job events."""
        ...

    def stream_job_output(self, job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream output for a specific job."""
        ...

    def stream_all_job_updates(self) -> AsyncGenerator[Any, None]:
        """Stream real-time job updates."""
        ...

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict[str, Any]:
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


class JobStreamServiceProtocol(Protocol):
    """Protocol for job output streaming services."""

    async def stream_job_output(self, job_id: str) -> AsyncGenerator[str, None]: ...
    async def stream_all_job_updates(self) -> AsyncGenerator[Dict[str, Any], None]: ...


class JobRenderServiceProtocol(Protocol):
    """Protocol for job rendering services."""

    async def render_jobs_html(self) -> str: ...
    async def stream_current_jobs_html(self) -> AsyncGenerator[str, None]: ...
    def get_jobs_for_display(self) -> List[Dict[str, Any]]: ...


class DebugServiceProtocol(Protocol):
    """Protocol for debug/diagnostics services."""

    def get_system_info(self) -> Dict[str, Any]: ...
    async def get_volume_info(self) -> Dict[str, Any]: ...
    def get_job_manager_info(self) -> Dict[str, Any]: ...
