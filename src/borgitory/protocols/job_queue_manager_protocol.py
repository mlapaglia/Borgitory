"""
Protocol for JobQueueManager - defines the interface for job queue management
"""

from typing import Protocol, Optional, List, Dict, Callable, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    # Import types only for type checking, not at runtime
    from borgitory.services.jobs.job_queue_manager import (
        JobPriority,
        QueuedJob,
        QueueStats,
    )


class JobQueueManagerProtocol(Protocol):
    """Protocol defining the interface for job queue management"""

    # Instance attributes
    max_concurrent_backups: int
    max_concurrent_operations: int
    queue_poll_interval: float

    async def enqueue_job(
        self,
        job_id: uuid.UUID,
        job_type: str,
        priority: "JobPriority" = ...,
        metadata: Optional[Dict[str, object]] = None,
    ) -> bool:
        """Add a job to the appropriate queue"""
        ...

    def set_callbacks(
        self,
        job_start_callback: Optional[Callable[[uuid.UUID, "QueuedJob"], None]] = None,
        job_complete_callback: Optional[Callable[[uuid.UUID, bool], None]] = None,
    ) -> None:
        """Set callbacks for job lifecycle events"""
        ...

    def get_queue_stats(self) -> "QueueStats":
        """Get current queue statistics"""
        ...

    def get_running_jobs(self) -> List[Dict[str, object]]:
        """Get list of currently running jobs"""
        ...

    async def initialize(self) -> None:
        """Initialize async resources"""
        ...

    async def shutdown(self) -> None:
        """Shutdown queue processors and clean up"""
        ...
