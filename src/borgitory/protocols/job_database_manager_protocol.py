"""
Protocol for JobDatabaseManager - defines the interface for job database management
"""

from typing import Protocol, Optional, List, Dict, Any, TYPE_CHECKING
import uuid
from datetime import datetime

if TYPE_CHECKING:
    # Import types only for type checking, not at runtime
    from borgitory.services.jobs.job_database_manager import DatabaseJobData
    from borgitory.services.jobs.job_models import BorgJobTask

from borgitory.models.job_results import JobStatusEnum


class JobDatabaseManagerProtocol(Protocol):
    """Protocol defining the interface for job database management"""

    def __init__(
        self,
        db_session_factory: Optional[Any] = None,
    ) -> None:
        """Initialize the database manager"""
        ...

    async def create_database_job(
        self, job_data: "DatabaseJobData"
    ) -> Optional[uuid.UUID]:
        """Create a new job record in the database"""
        ...

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatusEnum,
        finished_at: Optional[datetime] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update job status in database"""
        ...

    async def get_job_by_uuid(self, job_id: uuid.UUID) -> Optional[Dict[str, object]]:
        """Get job data by UUID"""
        ...

    async def get_jobs_by_repository(
        self, repository_id: int, limit: int = 50, job_type: Optional[str] = None
    ) -> List[Dict[str, object]]:
        """Get jobs for a specific repository"""
        ...

    async def get_repository_data(
        self, repository_id: int
    ) -> Optional[Dict[str, object]]:
        """Get repository data"""
        ...

    async def save_job_tasks(
        self, job_id: uuid.UUID, tasks: List["BorgJobTask"]
    ) -> bool:
        """Save task data for a job to the database"""
        ...

    async def get_job_statistics(self) -> Dict[str, object]:
        """Get job statistics"""
        ...
