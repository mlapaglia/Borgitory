"""
Job Manager Dependencies - Dependency injection structure for modular job management
"""
import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

from app.services.job_executor import JobExecutor
from app.services.job_output_manager import JobOutputManager
from app.services.job_queue_manager import JobQueueManager
from app.services.job_event_broadcaster import JobEventBroadcaster
from app.services.job_database_manager import JobDatabaseManager
from app.services.cloud_backup_coordinator import CloudBackupCoordinator


@dataclass
class JobManagerConfig:
    """Configuration for the modular job manager"""
    # Concurrency settings
    max_concurrent_backups: int = 5
    max_concurrent_operations: int = 10
    
    # Output and storage settings
    max_output_lines_per_job: int = 1000
    auto_cleanup_delay_seconds: int = 30
    
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
    job_executor: Optional[JobExecutor] = None
    output_manager: Optional[JobOutputManager] = None
    queue_manager: Optional[JobQueueManager] = None
    event_broadcaster: Optional[JobEventBroadcaster] = None
    database_manager: Optional[JobDatabaseManager] = None
    cloud_coordinator: Optional[CloudBackupCoordinator] = None
    
    # External dependencies (for testing/customization)
    subprocess_executor: Optional[Callable] = field(default_factory=lambda: asyncio.create_subprocess_exec)
    db_session_factory: Optional[Callable] = None
    rclone_service: Optional[Any] = None
    http_client_factory: Optional[Callable] = None
    
    def __post_init__(self):
        """Initialize default dependencies if not provided"""
        if self.db_session_factory is None:
            self.db_session_factory = self._default_db_session_factory
    
    def _default_db_session_factory(self):
        """Default database session factory"""
        from app.utils.db_session import get_db_session
        return get_db_session()


class JobManagerFactory:
    """Factory for creating job manager instances with proper dependency injection"""
    
    @classmethod
    def create_dependencies(
        self,
        config: Optional[JobManagerConfig] = None,
        custom_dependencies: Optional[JobManagerDependencies] = None
    ) -> JobManagerDependencies:
        """Create a complete set of dependencies for the job manager"""
        
        if config is None:
            config = JobManagerConfig()
        
        if custom_dependencies is None:
            custom_dependencies = JobManagerDependencies()
        
        # Create core services with proper configuration
        deps = JobManagerDependencies(
            # Use provided dependencies or create new ones
            subprocess_executor=custom_dependencies.subprocess_executor,
            db_session_factory=custom_dependencies.db_session_factory,
            rclone_service=custom_dependencies.rclone_service,
            http_client_factory=custom_dependencies.http_client_factory
        )
        
        # Job Executor
        if custom_dependencies.job_executor:
            deps.job_executor = custom_dependencies.job_executor
        else:
            deps.job_executor = JobExecutor(
                subprocess_executor=deps.subprocess_executor
            )
        
        # Job Output Manager
        if custom_dependencies.output_manager:
            deps.output_manager = custom_dependencies.output_manager
        else:
            deps.output_manager = JobOutputManager(
                max_lines_per_job=config.max_output_lines_per_job
            )
        
        # Job Queue Manager
        if custom_dependencies.queue_manager:
            deps.queue_manager = custom_dependencies.queue_manager
        else:
            deps.queue_manager = JobQueueManager(
                max_concurrent_backups=config.max_concurrent_backups,
                max_concurrent_operations=config.max_concurrent_operations,
                queue_poll_interval=config.queue_poll_interval
            )
        
        # Job Event Broadcaster
        if custom_dependencies.event_broadcaster:
            deps.event_broadcaster = custom_dependencies.event_broadcaster
        else:
            deps.event_broadcaster = JobEventBroadcaster(
                max_queue_size=config.sse_max_queue_size,
                keepalive_timeout=config.sse_keepalive_timeout
            )
        
        # Cloud Backup Coordinator
        if custom_dependencies.cloud_coordinator:
            deps.cloud_coordinator = custom_dependencies.cloud_coordinator
        else:
            deps.cloud_coordinator = CloudBackupCoordinator(
                db_session_factory=deps.db_session_factory,
                rclone_service=deps.rclone_service,
                http_client_factory=deps.http_client_factory
            )
        
        # Job Database Manager
        if custom_dependencies.database_manager:
            deps.database_manager = custom_dependencies.database_manager
        else:
            deps.database_manager = JobDatabaseManager(
                db_session_factory=deps.db_session_factory,
                cloud_backup_coordinator=deps.cloud_coordinator
            )
        
        return deps
    
    @classmethod
    def create_for_testing(
        self,
        mock_subprocess: Optional[Callable] = None,
        mock_db_session: Optional[Callable] = None,
        mock_rclone_service: Optional[Any] = None,
        mock_http_client: Optional[Callable] = None
    ) -> JobManagerDependencies:
        """Create dependencies with mocked services for testing"""
        
        test_deps = JobManagerDependencies(
            subprocess_executor=mock_subprocess,
            db_session_factory=mock_db_session,
            rclone_service=mock_rclone_service,
            http_client_factory=mock_http_client
        )
        
        return self.create_dependencies(custom_dependencies=test_deps)
    
    @classmethod
    def create_minimal(self) -> JobManagerDependencies:
        """Create minimal dependencies (useful for testing or simple use cases)"""
        
        config = JobManagerConfig(
            max_concurrent_backups=1,
            max_concurrent_operations=2,
            max_output_lines_per_job=100,
            sse_max_queue_size=10
        )
        
        return self.create_dependencies(config=config)


def get_default_job_manager_dependencies() -> JobManagerDependencies:
    """Get default job manager dependencies (production configuration)"""
    return JobManagerFactory.create_dependencies()


def get_test_job_manager_dependencies(
    mock_subprocess: Optional[Callable] = None,
    mock_db_session: Optional[Callable] = None,
    mock_rclone_service: Optional[Any] = None
) -> JobManagerDependencies:
    """Get job manager dependencies for testing"""
    return JobManagerFactory.create_for_testing(
        mock_subprocess=mock_subprocess,
        mock_db_session=mock_db_session,
        mock_rclone_service=mock_rclone_service
    )