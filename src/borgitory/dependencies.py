"""
FastAPI dependency providers for the application.
"""

from typing import (
    Annotated,
    TYPE_CHECKING,
    AsyncGenerator,
    Optional,
    Callable,
    Any,
    List,
    Coroutine,
)
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import async_session_maker
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.models.enums import EncryptionType
from borgitory.services.jobs.job_models import TaskStatusEnum, TaskTypeEnum
from borgitory.services.notifications.registry import get_metadata
from borgitory.services.path.path_configuration_service import PathConfigurationService

if TYPE_CHECKING:
    from borgitory.services.notifications.registry import NotificationProviderRegistry
    from borgitory.services.notifications.registry_factory import (
        NotificationRegistryFactory,
    )
    from borgitory.services.notifications.service import NotificationProviderFactory
    from borgitory.services.notifications.providers.discord_provider import HttpClient
    from borgitory.config.command_runner_config import CommandRunnerConfig
    from borgitory.config.job_manager_config import JobManagerEnvironmentConfig
    from borgitory.services.jobs.job_models import JobManagerConfig
    from borgitory.services.cloud_providers.registry_factory import RegistryFactory
    from borgitory.services.volumes.file_system_interface import FileSystemInterface
    from borgitory.protocols.repository_protocols import ArchiveServiceProtocol
    from borgitory.protocols.path_protocols import PathServiceInterface
    from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
    from borgitory.protocols.file_protocols import FileServiceProtocol
    from borgitory.services.command_execution.wsl_command_executor import (
        WSLCommandExecutor,
    )
from functools import lru_cache
from fastapi import Depends
from borgitory.utils.template_paths import get_template_directory
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.borg_service import BorgService
from borgitory.protocols.archive_manager_protocol import ArchiveManagerProtocol
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.jobs.job_service import JobService
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.recovery_service import RecoveryService
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.config_service import NotificationConfigService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.debug_service import DebugService
from borgitory.protocols.environment_protocol import DefaultEnvironment
from borgitory.services.rclone_service import RcloneService
from borgitory.services.encryption_service import EncryptionService
from borgitory.services.cloud_providers import StorageFactory
from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
)
from borgitory.services.scheduling.scheduler_service import SchedulerService
from borgitory.services.task_definition_builder import TaskDefinitionBuilder
from borgitory.services.package_manager_service import PackageManagerService
from borgitory.services.startup.package_restoration_service import (
    PackageRestorationService,
)
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
    get_job_event_broadcaster,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.hooks.hook_execution_service import HookExecutionService
from borgitory.services.configuration_service import ConfigurationService
from borgitory.services.repositories.repository_check_config_service import (
    RepositoryCheckConfigService,
)
from borgitory.services.prune_service import PruneService
from borgitory.services.cron_description_service import CronDescriptionService
from borgitory.services.upcoming_backups_service import UpcomingBackupsService
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.jobs.job_output_manager import JobOutputManager
from borgitory.services.jobs.job_queue_manager import JobQueueManager
from borgitory.services.jobs.job_database_manager import JobDatabaseManager
from fastapi.templating import Jinja2Templates
from starlette.templating import _TemplateResponse
from borgitory.utils.datetime_utils import (
    format_datetime_for_display,
    get_server_timezone,
)


from fastapi import Request
from datetime import datetime, timedelta


def datetime_browser_filter(
    dt: datetime,
    format_str: str = "%Y-%m-%d %H:%M:%S",
    tz_offset: Optional[int] = None,
) -> str:
    """Jinja2 filter for datetime formatting with browser timezone conversion"""
    if tz_offset is not None:
        return format_datetime_for_display(
            dt, format_str, browser_tz_offset_minutes=tz_offset
        )
    else:
        # Fallback to server timezone when no browser offset available
        return format_datetime_for_display(dt, format_str, get_server_timezone())


if TYPE_CHECKING:
    from borgitory.services.cloud_sync_service import CloudSyncConfigService
    from borgitory.protocols.command_protocols import (
        CommandRunnerProtocol,
        ProcessExecutorProtocol,
    )
    from borgitory.protocols.job_protocols import (
        JobManagerProtocol,
    )
    from borgitory.protocols.cloud_protocols import CloudSyncConfigServiceProtocol
    from borgitory.factories.service_factory import CloudProviderServiceFactory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_wsl_command_executor() -> "WSLCommandExecutor":
    """
    Provide a WSLCommandExecutor instance with proper FastAPI dependency injection.

    Returns:
        WSLCommandExecutor: WSL command executor instance for Windows WSL operations
    """
    from borgitory.services.command_execution.wsl_command_executor import (
        WSLCommandExecutor,
    )

    return WSLCommandExecutor()


def get_command_executor(
    wsl_executor: "WSLCommandExecutor" = Depends(get_wsl_command_executor),
) -> "CommandExecutorProtocol":
    """
    Provide a command executor for cross-platform command execution.

    This factory creates the appropriate command executor based on the environment:
    - Windows + WSL: WSLCommandExecutor (injected)
    - Linux/Docker: LinuxCommandExecutor

    Args:
        wsl_executor: Injected WSL command executor for Windows

    Returns:
        CommandExecutorProtocol: Platform-appropriate command executor
    """
    from borgitory.services.command_execution.command_executor_factory import (
        create_command_executor_with_injection,
    )

    return create_command_executor_with_injection(wsl_executor)


def get_subprocess_executor() -> Callable[
    ..., Coroutine[None, None, "asyncio.subprocess.Process"]
]:
    """
    Provide subprocess executor function for process creation (legacy).

    This factory creates subprocess processes using the asyncio event loop.
    This is kept for backward compatibility but new code should use get_command_executor.

    Returns:
        Callable: Function that creates subprocess processes (asyncio.create_subprocess_exec)
    """
    import asyncio

    return asyncio.create_subprocess_exec


def get_job_executor(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> "ProcessExecutorProtocol":
    """
    Provide a ProcessExecutorProtocol implementation (JobExecutor) with injected command executor.

    Args:
        command_executor: Injected command executor for cross-platform execution

    Returns:
        ProcessExecutorProtocol: JobExecutor instance with injected dependencies
    """
    return JobExecutor(command_executor)


def get_job_output_manager() -> JobOutputManager:
    """
    Provide a JobOutputManager instance.

    Request-scoped for better isolation between operations.
    Configuration loaded from environment per request.
    """
    import os

    max_lines = int(os.getenv("BORG_MAX_OUTPUT_LINES", "1000"))
    return JobOutputManager(max_lines_per_job=max_lines)


def get_job_queue_manager() -> JobQueueManager:
    """
    Provide a JobQueueManager instance.

    Request-scoped for better isolation between operations.
    Configuration loaded from environment per request.
    """
    import os

    return JobQueueManager(
        max_concurrent_backups=int(os.getenv("BORG_MAX_CONCURRENT_BACKUPS", "5")),
        max_concurrent_operations=int(
            os.getenv("BORG_MAX_CONCURRENT_OPERATIONS", "10")
        ),
        queue_poll_interval=float(os.getenv("BORG_QUEUE_POLL_INTERVAL", "0.1")),
    )


def get_job_database_manager() -> JobDatabaseManager:
    """
    Provide a JobDatabaseManager instance.

    Request-scoped for proper database session management.
    Uses default db_session_factory if none provided.
    """

    return JobDatabaseManager(async_session_maker)


def get_command_runner_config() -> "CommandRunnerConfig":
    """
    Provide CommandRunnerConfig from environment variables.

    Returns:
        CommandRunnerConfig: Configuration loaded from environment
    """
    from borgitory.config.command_runner_config import CommandRunnerConfig

    return CommandRunnerConfig.from_env()


def get_simple_command_runner(
    config: "CommandRunnerConfig" = Depends(get_command_runner_config),
    executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> "CommandRunnerProtocol":
    """
    Provide a CommandRunnerProtocol implementation with injected configuration.

    Args:
        config: Configuration for command runner behavior
        executor: Command executor for cross-platform execution

    Returns:
        CommandRunnerProtocol: Configured SimpleCommandRunner instance
    """
    from borgitory.services.simple_command_runner import SimpleCommandRunner

    return SimpleCommandRunner(config=config, executor=executor)


def get_http_client() -> "HttpClient":
    """
    Provide HTTP client instance with proper FastAPI dependency injection.

    Returns:
        HttpClient: New AiohttpClient instance for each request
    """
    from borgitory.services.notifications.providers.discord_provider import (
        AiohttpClient,
    )

    return AiohttpClient()


def get_notification_provider_factory(
    http_client: "HttpClient" = Depends(get_http_client),
) -> "NotificationProviderFactory":
    """
    Provide NotificationProviderFactory with injected HTTP client.

    Following the exact pattern of cloud providers' StorageFactory.
    """
    from borgitory.services.notifications.service import NotificationProviderFactory

    return NotificationProviderFactory(http_client=http_client)


@lru_cache()
def get_notification_service_singleton() -> NotificationService:
    """
    Create NotificationService singleton for application-scoped use.

    📋 USAGE:
    ✅ Use for: Singletons, direct instantiation, tests, JobManager
    ❌ Don't use for: FastAPI endpoints (use get_notification_service instead)

    📋 PATTERN: Dual Functions
    This is the singleton version that resolves dependencies directly.
    For FastAPI DI, use get_notification_service() with Depends().

    Returns:
        NotificationService: Cached singleton instance
    """
    from borgitory.services.notifications.service import NotificationService

    http_client = get_http_client()
    provider_factory = get_notification_provider_factory(http_client)
    return NotificationService(provider_factory=provider_factory)


def get_notification_service(
    provider_factory: "NotificationProviderFactory" = Depends(
        get_notification_provider_factory
    ),
) -> NotificationService:
    """
    Provide NotificationService with FastAPI dependency injection.

    📋 USAGE:
    ✅ Use for: FastAPI endpoints with Depends(get_notification_service)
    ❌ Don't use for: Direct calls, singletons, tests

    ⚠️  WARNING: This function should ONLY be called by FastAPI's DI system.
    ⚠️  For direct calls, use get_notification_service_singleton() instead.

    📋 PATTERN: Dual Functions
    This is the FastAPI DI version that expects resolved dependencies.
    For direct calls, use get_notification_service_singleton().

    Args:
        provider_factory: Injected by FastAPI DI system

    Returns:
        NotificationService: New instance with injected dependencies

    Raises:
        RuntimeError: If called directly with Depends object
    """
    # Add runtime check to catch misuse
    if hasattr(provider_factory, "dependency"):
        raise RuntimeError(
            "get_notification_service() was called directly with a Depends object. "
            "This indicates a bug in the dependency injection setup. "
            "Use get_notification_service_singleton() for direct calls instead."
        )

    return NotificationService(provider_factory=provider_factory)


def get_notification_config_service(
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationConfigService:
    """
    Provide a NotificationConfigService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return NotificationConfigService(notification_service=notification_service)


def get_rclone_service(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> RcloneService:
    """
    Provide a RcloneService instance with proper FastAPI dependency injection.

    Args:
        command_executor: Injected CommandExecutorProtocol instance

    Returns:
        RcloneService: New RcloneService instance for each request
    """
    return RcloneService(command_executor=command_executor)


def get_repository_stats_service(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> RepositoryStatsService:
    """
    Provide a RepositoryStatsService with injected command executor.

    Args:
        command_executor: Injected command executor for Borg operations

    Returns:
        RepositoryStatsService: Service instance with injected dependencies
    """
    return RepositoryStatsService(command_executor)


def get_file_system() -> "FileSystemInterface":
    """
    Provide FileSystemInterface implementation for filesystem operations.

    Returns:
        FileSystemInterface: OS-based filesystem implementation
    """
    from borgitory.services.volumes.os_file_system import OsFileSystem

    return OsFileSystem()


def get_path_configuration_service() -> "PathConfigurationService":
    """Get path configuration service."""
    from borgitory.services.path.path_configuration_service import (
        PathConfigurationService,
    )

    return PathConfigurationService()


def get_path_service(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> "PathServiceInterface":
    """
    Provide PathServiceInterface implementation for cross-platform path operations.

    This function creates a unified path service that uses the appropriate
    CommandExecutorProtocol based on the current platform.

    Returns:
        PathServiceInterface: Unified path service implementation
    """
    import logging
    from borgitory.services.path.path_service import PathService

    logger = logging.getLogger(__name__)
    config = get_path_configuration_service()

    logger.debug(
        f"Creating unified path service for {config.get_platform_name()} with {type(command_executor).__name__}"
    )
    return PathService(config, command_executor)


def get_hook_execution_service() -> HookExecutionService:
    """
    Provide a HookExecutionService instance with proper dependency injection.

    Uses SimpleCommandRunner as the command runner for consistent command execution.
    """
    command_runner_config = get_command_runner_config()
    wsl_executor = get_wsl_command_executor()
    command_executor = get_command_executor(wsl_executor)
    command_runner = get_simple_command_runner(command_runner_config, command_executor)
    return HookExecutionService(command_runner=command_runner)


def get_task_definition_builder() -> TaskDefinitionBuilder:
    """
    Provide a TaskDefinitionBuilder instance with database session.

    Note: This is not cached because it needs a database session per request.
    """
    return TaskDefinitionBuilder()


def get_job_event_broadcaster_dep() -> JobEventBroadcaster:
    """
    Provide the global JobEventBroadcaster instance.

    Note: This uses the global instance to ensure all components
    share the same event broadcaster.
    """
    return get_job_event_broadcaster()


def get_browser_timezone_offset(request: Request) -> Optional[int]:
    """
    Extract browser timezone offset from request cookies.

    Args:
        request: FastAPI request object

    Returns:
        Browser timezone offset in minutes, or None if not available
    """
    tz_cookie = request.cookies.get("browser_timezone_offset")
    if tz_cookie:
        try:
            return int(tz_cookie)
        except (ValueError, TypeError):
            pass
    return None


class TimezoneAwareJinja2Templates(Jinja2Templates):
    """
    Custom Jinja2Templates that automatically includes browser timezone offset in context.
    """

    def TemplateResponse(self, *args: Any, **kwargs: Any) -> _TemplateResponse:
        """
        Create template response with automatic timezone offset injection.
        """
        # Extract request and context from args/kwargs
        request = args[0] if len(args) > 0 else kwargs.get("request")
        context = args[2] if len(args) > 2 else kwargs.get("context", {})

        if context is None:
            context = {}

        # Automatically add browser timezone offset to context
        if request:
            context["browser_tz_offset"] = get_browser_timezone_offset(request)

        # Update context in kwargs if it was passed as kwarg, otherwise update args
        if len(args) > 2:
            args_list = list(args)
            args_list[2] = context
            args = tuple(args_list)
        else:
            kwargs["context"] = context

        return super().TemplateResponse(*args, **kwargs)


def get_templates() -> TimezoneAwareJinja2Templates:
    """
    Provide a TimezoneAwareJinja2Templates instance with custom filters and proper FastAPI dependency injection.

    Returns:
        TimezoneAwareJinja2Templates: New templates instance with custom filters for each request
    """
    template_path = get_template_directory()
    templates = TimezoneAwareJinja2Templates(directory=template_path)

    # Add custom datetime filters
    def datetime_filter(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Jinja2 filter for datetime formatting with timezone conversion"""
        return format_datetime_for_display(dt, format_str, get_server_timezone())

    # Use the standalone datetime_browser_filter function

    def from_json_filter(json_str: str) -> List[Any]:
        """Jinja2 filter for parsing JSON strings"""
        import json

        try:
            return json.loads(json_str) if json_str else []
        except (json.JSONDecodeError, TypeError):
            return []

    def to_json_filter(obj: Any) -> str:
        """Jinja2 filter for converting objects to JSON strings"""
        import json

        return json.dumps(obj) if obj is not None else '""'

    templates.env.filters["format_datetime"] = datetime_filter
    templates.env.filters["format_datetime_browser"] = datetime_browser_filter
    templates.env.filters["from_json"] = from_json_filter
    templates.env.filters["tojson"] = to_json_filter
    templates.env.globals["TaskStatusEnum"] = TaskStatusEnum
    templates.env.globals["TaskTypeEnum"] = TaskTypeEnum
    templates.env.globals["JobStatusEnum"] = JobStatusEnum
    templates.env.globals["JobTypeEnum"] = JobTypeEnum
    templates.env.globals["EncryptionType"] = EncryptionType

    return templates


def get_registry_factory() -> "RegistryFactory":
    """
    Provide RegistryFactory for creating provider registries.

    Returns:
        RegistryFactory: Factory for creating provider registries
    """
    from borgitory.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory()


def get_provider_registry(
    registry_factory: "RegistryFactory" = Depends(get_registry_factory),
) -> ProviderRegistry:
    """
    Provide ProviderRegistry with injected factory.

    Args:
        registry_factory: Injected factory for creating registries

    Returns:
        ProviderRegistry: Registry with all production providers registered
    """
    return registry_factory.create_production_registry()


def get_configuration_service() -> ConfigurationService:
    """
    Provide ConfigurationService.

    Returns:
        ConfigurationService: Configured service instance
    """
    return ConfigurationService()


def get_repository_check_config_service() -> RepositoryCheckConfigService:
    """
    Provide a RepositoryCheckConfigService instance.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return RepositoryCheckConfigService()


def get_prune_service() -> PruneService:
    """
    Provide a PruneService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return PruneService()


def get_cron_description_service() -> CronDescriptionService:
    """
    Provide a CronDescriptionService instance with proper FastAPI dependency injection.

    Returns:
        CronDescriptionService: New CronDescriptionService instance for each request
    """
    return CronDescriptionService()


def get_upcoming_backups_service(
    cron_description_service: CronDescriptionService = Depends(
        get_cron_description_service
    ),
) -> UpcomingBackupsService:
    """Provide UpcomingBackupsService instance."""
    return UpcomingBackupsService(cron_description_service)


def get_encryption_service() -> EncryptionService:
    """Provide an EncryptionService instance."""
    return EncryptionService()


def get_storage_factory(
    rclone: RcloneService = Depends(get_rclone_service),
) -> StorageFactory:
    """Provide a StorageFactory instance with injected RcloneService."""
    return StorageFactory(rclone)


def get_job_manager_env_config() -> "JobManagerEnvironmentConfig":
    """
    Provide JobManagerEnvironmentConfig from environment variables.

    Returns:
        JobManagerEnvironmentConfig: Configuration loaded from environment
    """
    from borgitory.config.job_manager_config import JobManagerEnvironmentConfig

    return JobManagerEnvironmentConfig.from_env()


def get_job_manager_config(
    env_config: "JobManagerEnvironmentConfig" = Depends(get_job_manager_env_config),
) -> "JobManagerConfig":
    """
    Provide JobManagerConfig with injected environment configuration.

    Args:
        env_config: Environment-based configuration values

    Returns:
        JobManagerConfig: Configured JobManager instance
    """
    from borgitory.services.jobs.job_models import JobManagerConfig

    return JobManagerConfig(
        max_concurrent_backups=env_config.max_concurrent_backups,
        max_output_lines_per_job=env_config.max_output_lines_per_job,
        max_concurrent_operations=env_config.max_concurrent_operations,
        queue_poll_interval=env_config.queue_poll_interval,
        sse_keepalive_timeout=env_config.sse_keepalive_timeout,
        sse_max_queue_size=env_config.sse_max_queue_size,
        max_concurrent_cloud_uploads=env_config.max_concurrent_cloud_uploads,
    )


@lru_cache()
def get_job_manager_singleton() -> "JobManagerProtocol":
    """
    Create JobManager singleton for application-scoped use.

    📋 USAGE:
    ✅ Use for: Singletons, direct instantiation, tests, background tasks
    ❌ Don't use for: FastAPI endpoints (use get_job_manager_dependency instead)

    📋 PATTERN: Dual Functions
    This is the singleton version that resolves dependencies directly.
    For FastAPI DI, use get_job_manager_dependency() with Depends().

    Returns:
        JobManagerProtocol: Cached singleton instance
    """
    from borgitory.services.jobs.job_models import JobManagerDependencies
    from borgitory.services.jobs.job_manager_factory import JobManagerFactory

    # Resolve all dependencies directly (not via FastAPI DI)
    env_config = get_job_manager_env_config()
    config = get_job_manager_config(env_config)
    wsl_executor = get_wsl_command_executor()
    command_executor = get_command_executor(wsl_executor)
    job_executor = get_job_executor(command_executor)
    output_manager = get_job_output_manager()
    queue_manager = get_job_queue_manager()
    database_manager = get_job_database_manager()
    event_broadcaster = get_job_event_broadcaster_dep()
    rclone_service = get_rclone_service(command_executor)
    notification_service = get_notification_service_singleton()  # Use singleton version
    encryption_service = get_encryption_service()
    storage_factory = get_storage_factory(rclone_service)
    registry_factory = get_registry_factory()
    provider_registry = get_provider_registry(registry_factory)
    hook_execution_service = get_hook_execution_service()

    # Create dependencies using resolved services
    custom_dependencies = JobManagerDependencies(
        job_executor=job_executor,
        output_manager=output_manager,
        queue_manager=queue_manager,
        database_manager=database_manager,
        event_broadcaster=event_broadcaster,
        rclone_service=rclone_service,
        notification_service=notification_service,
        encryption_service=encryption_service,
        storage_factory=storage_factory,
        provider_registry=provider_registry,
        hook_execution_service=hook_execution_service,
        async_session_maker=async_session_maker,
        http_client_factory=lambda: HttpClient(),  # type: ignore
    )

    # Use the factory to ensure all dependencies are properly initialized
    dependencies = JobManagerFactory.create_dependencies(
        config=config, custom_dependencies=custom_dependencies
    )

    return JobManager(config=config, dependencies=dependencies)


def get_job_manager_dependency() -> "JobManagerProtocol":
    """
    Provide JobManager with FastAPI dependency injection.

    📋 USAGE:
    ✅ Use for: FastAPI endpoints with Depends(get_job_manager_dependency)
    ❌ Don't use for: Direct calls, singletons, tests

    ⚠️  WARNING: This function should ONLY be called by FastAPI's DI system.
    ⚠️  For direct calls, use get_job_manager_singleton() instead.

    📋 PATTERN: Dual Functions
    This is the FastAPI DI version that returns the same singleton instance.
    For direct calls, use get_job_manager_singleton().

    Returns:
        JobManagerProtocol: The same singleton instance as get_job_manager_singleton()
    """
    # Both functions return the same singleton instance
    # This ensures job state consistency across all usage patterns
    return get_job_manager_singleton()


@lru_cache()
def get_scheduler_service_singleton() -> SchedulerService:
    """
    Create SchedulerService singleton for application-scoped use.

    📋 USAGE:
    ✅ Use for: Singletons, direct instantiation, tests, background tasks, application lifecycle
    ❌ Don't use for: FastAPI endpoints (use get_scheduler_service_dependency instead)

    📋 PATTERN: Dual Functions
    This is the singleton version that resolves dependencies directly.
    For FastAPI DI, use get_scheduler_service_dependency() with Depends().

    Returns:
        SchedulerService: Cached singleton instance
    """
    # Resolve dependencies directly (not via FastAPI DI)
    job_manager = get_job_manager_singleton()
    job_service = get_job_service()
    return SchedulerService(
        job_manager=job_manager,
        job_service=job_service,
    )


def get_scheduler_service_dependency() -> SchedulerService:
    """
    Provide SchedulerService with FastAPI dependency injection.

    📋 USAGE:
    ✅ Use for: FastAPI endpoints with Depends(get_scheduler_service_dependency)
    ❌ Don't use for: Direct calls, singletons, tests

    ⚠️  WARNING: This function should ONLY be called by FastAPI's DI system.
    ⚠️  For direct calls, use get_scheduler_service_singleton() instead.

    📋 PATTERN: Dual Functions
    This is the FastAPI DI version that returns the same singleton instance.
    For direct calls, use get_scheduler_service_singleton().

    Returns:
        SchedulerService: The same singleton instance as get_scheduler_service_singleton()
    """
    # Both functions return the same singleton instance
    # This ensures scheduler state consistency across all usage patterns
    return get_scheduler_service_singleton()


def get_schedule_service(
    scheduler_service: SchedulerService = Depends(get_scheduler_service_dependency),
) -> ScheduleService:
    """
    Provide a ScheduleService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return ScheduleService(scheduler_service=scheduler_service)


def get_job_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> JobService:
    """
    Provide a JobService instance with database session injection.

    Note: This creates a new instance per request since it depends on the database session.
    """
    return JobService(job_manager)


def get_job_stream_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
) -> JobStreamService:
    """
    Provide a JobStreamService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return JobStreamService(job_manager)


def get_job_render_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
    templates: Jinja2Templates = Depends(get_templates),
) -> JobRenderService:
    """
    Provide a JobRenderService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return JobRenderService(job_manager=job_manager, templates=templates)


def get_debug_service(
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> DebugService:
    """
    Provide a DebugService instance with proper dependency injection.
    Uses FastAPI DI with automatic dependency resolution.
    """
    return DebugService(
        job_manager=job_manager,
        environment=DefaultEnvironment(),
        command_executor=command_executor,
    )


def get_cloud_provider_service_factory(
    rclone_service: RcloneService = Depends(get_rclone_service),
    storage_factory: StorageFactory = Depends(get_storage_factory),
    encryption_service: EncryptionService = Depends(get_encryption_service),
) -> "CloudProviderServiceFactory":
    """
    Provide CloudProviderServiceFactory with proper FastAPI dependency injection.

    Args:
        rclone_service: Injected RcloneService instance
        storage_factory: Injected StorageFactory instance
        encryption_service: Injected EncryptionService instance

    Returns:
        CloudProviderServiceFactory: Configured factory instance
    """
    return CloudProviderServiceFactory(
        rclone_service=rclone_service,
        storage_factory=storage_factory,
        encryption_service=encryption_service,
        metadata_func=get_metadata,
    )


def get_cloud_sync_service(
    factory: "CloudProviderServiceFactory" = Depends(
        get_cloud_provider_service_factory
    ),
) -> "CloudSyncConfigServiceProtocol":
    """
    Provide a CloudSyncConfigService instance using factory pattern with proper DI.

    Request-scoped since it depends on database session.
    Uses factory for consistent DI pattern across all services.
    """

    return factory.create_cloud_sync_service("default")


# 📋 SEMANTIC TYPE ALIASES FOR DEPENDENCY INJECTION
#
# These type aliases express the INTENDED USAGE PATTERN and LIFECYCLE:
# - ApplicationScoped* = Singleton instances for app-wide services (JobManager, background tasks)
# - RequestScoped* = Per-request instance via FastAPI DI (API endpoints)
#
# This makes the architectural intent crystal clear and prevents misuse.

# Core Services - Request Scoped (FastAPI Endpoints)
RequestScopedSimpleCommandRunner = Annotated[
    "CommandRunnerProtocol", Depends(get_simple_command_runner)
]

RequestScopedJobService = Annotated[JobService, Depends(get_job_service)]

ApplicationScopedNotificationService = NotificationService  # Application-wide singleton
RequestScopedNotificationService = Annotated[
    NotificationService, Depends(get_notification_service)
]

ApplicationScopedJobManager = "JobManagerProtocol"  # Application-wide singleton
RequestScopedJobManager = Annotated[
    "JobManagerProtocol", Depends(get_job_manager_dependency)
]

SimpleCommandRunnerDep = RequestScopedSimpleCommandRunner
JobServiceDep = RequestScopedJobService
JobManagerDep = RequestScopedJobManager
NotificationConfigServiceDep = Annotated[
    NotificationConfigService, Depends(get_notification_config_service)
]


def get_notification_registry_factory() -> "NotificationRegistryFactory":
    """
    Provide a NotificationRegistryFactory instance with proper FastAPI dependency injection.

    Returns:
        NotificationRegistryFactory: Factory for creating registries
    """
    from borgitory.services.notifications.registry_factory import (
        NotificationRegistryFactory,
    )

    return NotificationRegistryFactory()


def get_notification_provider_registry(
    factory: "NotificationRegistryFactory" = Depends(get_notification_registry_factory),
) -> "NotificationProviderRegistry":
    """
    Provide a NotificationProviderRegistry instance with proper FastAPI dependency injection.

    Args:
        factory: NotificationRegistryFactory instance from DI

    Returns:
        NotificationProviderRegistry: Registry with all production providers registered
    """
    return factory.create_production_registry()


NotificationRegistryFactoryDep = Annotated[
    "NotificationRegistryFactory", Depends(get_notification_registry_factory)
]
NotificationProviderRegistryDep = Annotated[
    "NotificationProviderRegistry", Depends(get_notification_provider_registry)
]
HttpClientDep = Annotated["HttpClient", Depends(get_http_client)]
NotificationProviderFactoryDep = Annotated[
    "NotificationProviderFactory", Depends(get_notification_provider_factory)
]
CloudProviderServiceFactoryDep = Annotated[
    "CloudProviderServiceFactory", Depends(get_cloud_provider_service_factory)
]
JobStreamServiceDep = Annotated[JobStreamService, Depends(get_job_stream_service)]
JobRenderServiceDep = Annotated[JobRenderService, Depends(get_job_render_service)]
DebugServiceDep = Annotated[DebugService, Depends(get_debug_service)]
RcloneServiceDep = Annotated[RcloneService, Depends(get_rclone_service)]
WSLCommandExecutorDep = Annotated[
    "WSLCommandExecutor", Depends(get_wsl_command_executor)
]
CommandExecutorDep = Annotated["CommandExecutorProtocol", Depends(get_command_executor)]
RepositoryStatsServiceDep = Annotated[
    RepositoryStatsService, Depends(get_repository_stats_service)
]
SchedulerServiceDep = Annotated[
    SchedulerService, Depends(get_scheduler_service_dependency)
]
TaskDefinitionBuilderDep = Annotated[
    TaskDefinitionBuilder, Depends(get_task_definition_builder)
]
JobEventBroadcasterDep = Annotated[
    JobEventBroadcaster, Depends(get_job_event_broadcaster_dep)
]
TemplatesDep = Annotated[Jinja2Templates, Depends(get_templates)]
ScheduleServiceDep = Annotated[ScheduleService, Depends(get_schedule_service)]
ConfigurationServiceDep = Annotated[
    ConfigurationService, Depends(get_configuration_service)
]
RepositoryCheckConfigServiceDep = Annotated[
    RepositoryCheckConfigService, Depends(get_repository_check_config_service)
]
JobExecutorDep = Annotated[JobExecutor, Depends(get_job_executor)]
JobOutputManagerDep = Annotated[JobOutputManager, Depends(get_job_output_manager)]
JobQueueManagerDep = Annotated[JobQueueManager, Depends(get_job_queue_manager)]
JobDatabaseManagerDep = Annotated[JobDatabaseManager, Depends(get_job_database_manager)]
EncryptionServiceDep = Annotated[EncryptionService, Depends(get_encryption_service)]
StorageFactoryDep = Annotated[StorageFactory, Depends(get_storage_factory)]
PruneServiceDep = Annotated[PruneService, Depends(get_prune_service)]
CronDescriptionServiceDep = Annotated[
    CronDescriptionService, Depends(get_cron_description_service)
]
UpcomingBackupsServiceDep = Annotated[
    UpcomingBackupsService, Depends(get_upcoming_backups_service)
]
CloudSyncServiceDep = Annotated[
    "CloudSyncConfigService", Depends(get_cloud_sync_service)
]
HookExecutionServiceDep = Annotated[
    HookExecutionService, Depends(get_hook_execution_service)
]
ProviderRegistryDep = Annotated[ProviderRegistry, Depends(get_provider_registry)]
PathServiceDep = Annotated["PathServiceInterface", Depends(get_path_service)]


@lru_cache()
def get_archive_manager_singleton() -> ArchiveManagerProtocol:
    """
    Create ArchiveManager singleton for application-scoped use.

    📋 USAGE:
    ✅ Use for: Singletons, direct instantiation, tests, background tasks
    ❌ Don't use for: FastAPI endpoints (use get_archive_manager_dependency instead)

    📋 PATTERN: Dual Functions
    This is the singleton version that resolves dependencies directly.
    For FastAPI DI, use get_archive_manager_dependency() with Depends().

    Returns:
        ArchiveManagerProtocol: Cached singleton instance with persistent cache state
    """
    # Resolve dependencies directly (not via FastAPI DI)
    wsl_executor = get_wsl_command_executor()
    command_executor = get_command_executor(wsl_executor)
    job_executor = get_job_executor(command_executor)

    return ArchiveManager(
        job_executor=job_executor,
        command_executor=command_executor,
        cache_ttl=timedelta(minutes=30),
    )


def get_archive_manager_dependency() -> ArchiveManagerProtocol:
    """
    Provide ArchiveManager with FastAPI dependency injection.

    📋 USAGE:
    ✅ Use for: FastAPI endpoints with Depends(get_archive_manager_dependency)
    ❌ Don't use for: Direct calls, singletons, tests

    ⚠️  WARNING: This function should ONLY be called by FastAPI's DI system.
    ⚠️  For direct calls, use get_archive_manager_singleton() instead.

    📋 PATTERN: Dual Functions
    This is the FastAPI DI version that returns the same singleton instance.
    For direct calls, use get_archive_manager_singleton().

    Returns:
        ArchiveManagerProtocol: The same singleton instance as get_archive_manager_singleton()
    """
    # Both functions return the same singleton instance
    # This ensures cache state consistency across all usage patterns
    return get_archive_manager_singleton()


def get_archive_service(
    archive_manager: ArchiveManagerProtocol = Depends(get_archive_manager_dependency),
) -> "ArchiveServiceProtocol":
    """
    Provide ArchiveManager service for archive operations.

    Returns:
        ArchiveServiceProtocol: Archive service implementation
    """
    return archive_manager


def get_file_service(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> "FileServiceProtocol":
    """
    Provide a FileService instance for file operations.

    Returns:
        FileServiceProtocol: File service implementation
    """
    from borgitory.services.files.file_service_factory import create_file_service

    return create_file_service(command_executor)


def get_borg_service(
    job_executor: "ProcessExecutorProtocol" = Depends(get_job_executor),
    command_runner: "CommandRunnerProtocol" = Depends(get_simple_command_runner),
    job_manager: "JobManagerProtocol" = Depends(get_job_manager_dependency),
    archive_service: "ArchiveServiceProtocol" = Depends(get_archive_service),
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> BorgService:
    """
    Provide BorgService with all mandatory dependencies injected.

    Args:
        job_executor: Injected job executor for running Borg processes
        command_runner: Injected command runner for system commands
        job_manager: Injected job manager for job lifecycle
        archive_service: Injected archive service for archive operations
        command_executor: Injected command executor for cross-platform execution
        file_service: Injected file service for file operations

    Returns:
        BorgService: Fully configured service with all dependencies
    """
    return BorgService(
        job_executor=job_executor,
        command_runner=command_runner,
        job_manager=job_manager,
        archive_service=archive_service,
        command_executor=command_executor,
    )


def get_archive_manager(
    job_executor: JobExecutor = Depends(get_job_executor),
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> ArchiveManagerProtocol:
    """
    Provide an ArchiveManager instance with proper dependency injection.

    Uses the factory to create the appropriate archive manager implementation.
    Defaults to borg list-based manager for better reliability.

    Note: This creates a new instance per request. For singleton behavior,
    use get_archive_manager_dependency() instead.
    """
    return ArchiveManager(
        job_executor=job_executor,
        command_executor=command_executor,
        cache_ttl=timedelta(minutes=30),
    )


def get_recovery_service(
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
) -> RecoveryService:
    """
    Provide a RecoveryService instance with proper FastAPI dependency injection.

    Args:
        command_executor: Injected command executor for cross-platform execution
        borg_service: Injected borg service for repository operations

    Returns:
        RecoveryService: New RecoveryService instance for each request
    """
    return RecoveryService(
        command_executor=command_executor, session_maker=async_session_maker
    )


RequestScopedRecoveryService = Annotated[RecoveryService, Depends(get_recovery_service)]
RecoveryServiceDep = RequestScopedRecoveryService


def get_repository_service(
    borg_service: BorgService = Depends(get_borg_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service_dependency),
    path_service: "PathServiceInterface" = Depends(get_path_service),
    command_executor: "CommandExecutorProtocol" = Depends(get_command_executor),
    file_service: "FileServiceProtocol" = Depends(get_file_service),
) -> RepositoryService:
    """
    Provide a RepositoryService instance with proper dependency injection.

    Uses FastAPI DI with automatic dependency resolution.
    """
    return RepositoryService(
        borg_service=borg_service,
        scheduler_service=scheduler_service,
        path_service=path_service,
        command_executor=command_executor,
        file_service=file_service,
    )


RequestScopedBorgService = Annotated[BorgService, Depends(get_borg_service)]
BorgServiceDep = RequestScopedBorgService
ArchiveManagerDep = Annotated[
    ArchiveManagerProtocol, Depends(get_archive_manager_dependency)
]
RepositoryServiceDep = Annotated[RepositoryService, Depends(get_repository_service)]


def get_package_manager_service(
    command_runner: "CommandRunnerProtocol" = Depends(get_simple_command_runner),
) -> PackageManagerService:
    """Get PackageManagerService instance with database session."""
    return PackageManagerService(command_runner=command_runner)


PackageManagerServiceDep = Annotated[
    PackageManagerService, Depends(get_package_manager_service)
]


def get_package_restoration_service(
    package_manager: PackageManagerServiceDep,
) -> PackageRestorationService:
    """Get PackageRestorationService instance with injected dependencies."""
    return PackageRestorationService(package_manager=package_manager)


PackageRestorationServiceDep = Annotated[
    PackageRestorationService, Depends(get_package_restoration_service)
]


def get_package_restoration_service_for_startup() -> PackageRestorationService:
    """
    Create PackageRestorationService for application startup.

    This creates its own database session context for the restoration process.
    Uses the same pattern as other startup services.
    """

    # The service will manage its own database session during restoration
    from borgitory.config.command_runner_config import CommandRunnerConfig
    from borgitory.services.command_execution.command_executor_factory import (
        create_command_executor,
    )

    config = CommandRunnerConfig()
    executor = create_command_executor()
    command_runner = SimpleCommandRunner(config=config, executor=executor)
    package_manager = PackageManagerService(command_runner=command_runner)
    return PackageRestorationService(package_manager=package_manager)
