"""
Job Manager Models - Data structures and configuration for job management
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import (
    Union,
    Dict,
    Optional,
    List,
    Callable,
    Coroutine,
    TYPE_CHECKING,
)
from dataclasses import dataclass, field
from contextlib import _GeneratorContextManager

from borgitory.models.job_results import JobStatusEnum


if TYPE_CHECKING:
    from asyncio.subprocess import Process
    from borgitory.models.database import Schedule


class TaskTypeEnum(str, Enum):
    """Task type enumeration"""

    BACKUP = "backup"
    PRUNE = "prune"
    CHECK = "check"
    CLOUD_SYNC = "cloud_sync"
    NOTIFICATION = "notification"
    HOOK = "hook"
    COMMAND = "command"
    INFO = "info"


class TaskStatusEnum(str, Enum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    QUEUED = "queued"
    STOPPED = "stopped"


if TYPE_CHECKING:
    from borgitory.protocols.command_protocols import ProcessExecutorProtocol
    from borgitory.dependencies import ApplicationScopedNotificationService
    from sqlalchemy.orm import Session
    from borgitory.services.notifications.providers.discord_provider import HttpClient
    from borgitory.services.cloud_providers import StorageFactory
    from borgitory.services.encryption_service import EncryptionService
    from borgitory.services.cloud_providers.registry import ProviderRegistry
    from borgitory.services.hooks.hook_execution_service import HookExecutionService
    from borgitory.services.rclone_service import RcloneService
    from borgitory.services.jobs.job_output_manager import JobOutputManager
    from borgitory.services.jobs.job_queue_manager import JobQueueManager
    from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
        JobEventBroadcaster,
    )
    from borgitory.services.jobs.job_database_manager import JobDatabaseManager


@dataclass
class JobManagerConfig:
    """Configuration for the job manager"""

    # Concurrency settings
    max_concurrent_backups: int = 5
    max_concurrent_operations: int = 10

    # Output and storage settings
    max_output_lines_per_job: int = 1000

    # Queue settings
    queue_poll_interval: float = 0.1

    # SSE settings
    sse_keepalive_timeout: float = 30.0
    sse_max_queue_size: int = 100

    # Cloud backup settings
    max_concurrent_cloud_uploads: int = 3


@dataclass
class JobManagerDependencies:
    """Injectable dependencies for the job manager"""

    # Core services
    job_executor: Optional["ProcessExecutorProtocol"] = None
    output_manager: Optional["JobOutputManager"] = None
    queue_manager: Optional["JobQueueManager"] = None
    event_broadcaster: Optional["JobEventBroadcaster"] = None
    database_manager: Optional["JobDatabaseManager"] = None

    # External dependencies (for testing/customization)
    subprocess_executor: Optional[Callable[..., Coroutine[None, None, "Process"]]] = (
        field(default_factory=lambda: asyncio.create_subprocess_exec)
    )
    db_session_factory: Optional[Callable[[], _GeneratorContextManager["Session"]]] = (
        None
    )
    rclone_service: Optional["RcloneService"] = None
    http_client_factory: Optional[Callable[[], "HttpClient"]] = None
    encryption_service: Optional["EncryptionService"] = None
    storage_factory: Optional["StorageFactory"] = None
    provider_registry: Optional["ProviderRegistry"] = None
    # Use semantic type alias for application-scoped notification service
    notification_service: Optional["ApplicationScopedNotificationService"] = None
    hook_execution_service: Optional["HookExecutionService"] = None

    def __post_init__(self) -> None:
        """Initialize default dependencies if not provided"""
        if self.db_session_factory is None:
            self.db_session_factory = self._default_db_session_factory

    def _default_db_session_factory(self) -> _GeneratorContextManager["Session"]:
        """Default database session factory"""
        from borgitory.utils.db_session import get_db_session

        return get_db_session()


@dataclass
class BorgJobTask:
    """Individual task within a job"""

    task_type: TaskTypeEnum
    task_name: str
    status: TaskStatusEnum = TaskStatusEnum.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    parameters: Dict[str, object] = field(default_factory=dict)
    output_lines: List[Union[str, Dict[str, str]]] = field(
        default_factory=list
    )  # Store task output


@dataclass
class BorgJob:
    """Represents a job in the manager"""

    id: str
    status: JobStatusEnum
    started_at: datetime
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None

    command: Optional[List[str]] = None

    job_type: str = "simple"  # 'simple' or 'composite'
    tasks: List[BorgJobTask] = field(default_factory=list)
    current_task_index: int = 0

    repository_id: Optional[int] = None
    schedule: Optional["Schedule"] = None

    cloud_sync_config_id: Optional[int] = None

    def get_current_task(self) -> Optional[BorgJobTask]:
        """Get the currently executing task (for composite jobs)"""
        if self.job_type == "composite" and 0 <= self.current_task_index < len(
            self.tasks
        ):
            return self.tasks[self.current_task_index]
        return None
