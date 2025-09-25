"""Job Manager environment configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class JobManagerEnvironmentConfig:
    """Environment-based configuration for JobManager."""

    max_concurrent_backups: int = 5
    max_output_lines_per_job: int = 1000
    max_concurrent_operations: int = 10
    queue_poll_interval: float = 0.1
    sse_keepalive_timeout: float = 30.0
    sse_max_queue_size: int = 100
    max_concurrent_cloud_uploads: int = 3

    @classmethod
    def from_env(cls) -> "JobManagerEnvironmentConfig":
        """Create configuration from environment variables."""
        return cls(
            max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
            max_output_lines_per_job=int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000")),
            max_concurrent_operations=int(
                os.getenv("BORG_MAX_CONCURRENT_OPERATIONS", "10")
            ),
            queue_poll_interval=float(os.getenv("BORG_QUEUE_POLL_INTERVAL", "0.1")),
            sse_keepalive_timeout=float(
                os.getenv("BORG_SSE_KEEPALIVE_TIMEOUT", "30.0")
            ),
            sse_max_queue_size=int(os.getenv("BORG_SSE_MAX_QUEUE_SIZE", "100")),
            max_concurrent_cloud_uploads=int(
                os.getenv("BORG_MAX_CONCURRENT_CLOUD_UPLOADS", "3")
            ),
        )
