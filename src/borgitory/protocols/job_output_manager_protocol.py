"""
Protocol for JobOutputManager - defines the interface for job output management
"""

from typing import Protocol, List, Optional, Dict, AsyncGenerator, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    # Import types only for type checking, not at runtime
    from borgitory.services.jobs.job_output_manager import (
        JobOutput,
        JobOutputStreamResponse,
    )


class JobOutputManagerProtocol(Protocol):
    """Protocol defining the interface for job output management"""

    def __init__(self, max_lines_per_job: int = 1000) -> None:
        """Initialize the output manager"""
        ...

    def create_job_output(self, job_id: uuid.UUID) -> "JobOutput":
        """Create output container for a new job"""
        ...

    async def add_output_line(
        self,
        job_id: uuid.UUID,
        text: str,
        line_type: str = "stdout",
        progress_info: Optional[Dict[str, object]] = None,
    ) -> None:
        """Add an output line for a specific job"""
        ...

    def get_job_output(self, job_id: uuid.UUID) -> Optional["JobOutput"]:
        """Get output container for a job"""
        ...

    async def get_job_output_stream(
        self, job_id: uuid.UUID
    ) -> "JobOutputStreamResponse":
        """Get formatted output data for API responses"""
        ...

    def stream_job_output(
        self, job_id: uuid.UUID, follow: bool = True
    ) -> AsyncGenerator[Dict[str, object], None]:
        """Stream job output in real-time"""
        ...

    def get_output_summary(self, job_id: uuid.UUID) -> Dict[str, object]:
        """Get summary of job output"""
        ...

    def clear_job_output(self, job_id: uuid.UUID) -> bool:
        """Clear output data for a job"""
        ...

    def get_all_job_outputs(self) -> Dict[uuid.UUID, Dict[str, object]]:
        """Get summary of all job outputs"""
        ...

    async def format_output_for_display(
        self,
        job_id: uuid.UUID,
        max_lines: Optional[int] = None,
        filter_type: Optional[str] = None,
    ) -> List[str]:
        """Format job output for display purposes"""
        ...

    def cleanup_old_outputs(self, max_age_seconds: int = 3600) -> int:
        """Clean up old job outputs"""
        ...
