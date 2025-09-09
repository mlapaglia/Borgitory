"""
Borg Job Manager - Now Uses Modular Architecture

This file is now the main entry point for the modular job manager system.
All services have been migrated to use the modular architecture directly.
"""

# Direct imports from modular version (no more backward compatibility wrapper)
from app.services.job_manager_modular import (
    ModularBorgJobManager,
    JobManagerConfig,
    BorgJob,
    BorgJobTask,
    get_job_manager,
    reset_job_manager,
)

# Export the modular types directly
__all__ = [
    "ModularBorgJobManager",
    "JobManagerConfig",
    "BorgJob",
    "BorgJobTask",
    "get_job_manager",
    "reset_job_manager",
]

# Legacy aliases - will be removed in future version
BorgJobManager = ModularBorgJobManager


# Backward compatible config wrapper
class BorgJobManagerConfig:
    """Backward compatible configuration wrapper"""

    def __init__(
        self,
        max_concurrent_backups: int = 5,
        auto_cleanup_delay: int = 30,
        max_output_lines: int = 1000,
        queue_poll_interval: float = 0.1,
        sse_keepalive_timeout: float = 30.0,
    ):
        # Store old-style attributes for compatibility
        self.max_concurrent_backups = max_concurrent_backups
        self.auto_cleanup_delay = auto_cleanup_delay
        self.max_output_lines = max_output_lines
        self.queue_poll_interval = queue_poll_interval
        self.sse_keepalive_timeout = sse_keepalive_timeout

        # Create the new config internally
        self._internal_config = JobManagerConfig(
            max_concurrent_backups=max_concurrent_backups,
            auto_cleanup_delay_seconds=auto_cleanup_delay,
            max_output_lines_per_job=max_output_lines,
            queue_poll_interval=queue_poll_interval,
            sse_keepalive_timeout=sse_keepalive_timeout,
        )

    def to_internal_config(self) -> JobManagerConfig:
        """Convert to internal modular config"""
        return self._internal_config
