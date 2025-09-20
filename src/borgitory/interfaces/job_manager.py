"""
Job manager protocol interfaces.

Defines the contracts for job management and execution services.
"""

from typing import Protocol, Dict, Any, List, Optional


class JobExecutor(Protocol):
    """Protocol for job execution services"""

    async def start_process(
        self, command: List[str], env: Optional[Dict[str, str]] = None
    ) -> Any:
        """Start a process for the given command"""
        ...

    async def monitor_process_output(
        self, process: Any, output_callback: Optional[Any] = None
    ) -> Any:
        """Monitor process output and return result"""
        ...

    async def terminate_process(self, process: Any) -> bool:
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
        task_definitions: List[Dict[str, Any]],
        repository: Any,
        schedule: Optional[Any] = None,
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

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status information for a job"""
        ...

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get job output stream data"""
        ...

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        ...

    def cleanup_job(self, job_id: str) -> bool:
        """Clean up job resources"""
        ...

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        ...
