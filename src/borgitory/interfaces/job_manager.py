"""
Job manager protocol interfaces.

Defines the contracts for job management and execution services.
"""

from typing import Protocol, Dict, List, Optional, TYPE_CHECKING

from borgitory.custom_types import ConfigDict

if TYPE_CHECKING:
    from borgitory.models.database import Repository, Schedule


class JobExecutor(Protocol):
    """Protocol for job execution services"""

    async def start_process(
        self, command: List[str], env: Optional[Dict[str, str]] = None
    ) -> object:
        """Start a process for the given command"""
        ...

    async def monitor_process_output(
        self, process: object, output_callback: Optional[object] = None
    ) -> object:
        """Monitor process output and return result"""
        ...

    async def terminate_process(self, process: object) -> bool:
        """Terminate a running process"""
        ...


class JobManager(Protocol):
    """Protocol for job management services"""

    async def start_borg_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        is_backup: bool = False,
    ) -> str:
        """
        Start a Borg command and return job ID.
        Args:
            command: Command to execute
            env: Environment variables
            is_backup: Whether this is a backup operation
        Returns:
            Job ID for tracking
        """
        ...

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List[ConfigDict],
        repository: "Repository",
        schedule: Optional["Schedule"] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """
        Create a composite job with multiple tasks.
        Args:
            job_type: Type of job
            task_definitions: List of task definitions
            repository: Repository object
            schedule: Optional schedule
            cloud_sync_config_id: Optional cloud sync config ID
        Returns:
            Job ID for tracking
        """
        ...

    def get_job_status(self, job_id: str) -> Optional[ConfigDict]:
        """Get status information for a job"""
        ...

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> ConfigDict:
        """Get job output stream data"""
        ...

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        ...

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job resources"""
        ...

    def get_queue_stats(self) -> ConfigDict:
        """Get queue statistics"""
        ...
