"""
Protocol-based service factory for creating services dynamically.

This factory enables runtime service creation based on protocols,
supporting different implementations and configurations.
"""

from typing import Type, Dict, Any, Optional, TypeVar, Generic
from abc import ABC
import logging

# Import our protocols
from borgitory.protocols.command_protocols import CommandRunnerProtocol
from borgitory.protocols.repository_protocols import BackupServiceProtocol
from borgitory.protocols.notification_protocols import NotificationServiceProtocol

logger = logging.getLogger(__name__)

# Generic protocol type
P = TypeVar("P")


class ServiceFactory(Generic[P], ABC):
    """Base factory for creating protocol-compliant services."""

    def __init__(self) -> None:
        self._implementations: Dict[str, Type[P]] = {}
        self._configurations: Dict[str, Dict[str, Any]] = {}
        self._default_implementation: Optional[str] = None

    def register_implementation(
        self,
        name: str,
        implementation: Type[P],
        config: Optional[Dict[str, Any]] = None,
        set_as_default: bool = False,
    ) -> None:
        """Register a service implementation."""
        self._implementations[name] = implementation
        if config:
            self._configurations[name] = config

        if set_as_default or not self._default_implementation:
            self._default_implementation = name

        logger.info(f"Registered {implementation.__name__} as '{name}' implementation")

    def create_service(
        self, implementation_name: Optional[str] = None, **kwargs: Any
    ) -> P:
        """Create a service instance."""
        name = implementation_name or self._default_implementation

        if not name or name not in self._implementations:
            available = list(self._implementations.keys())
            raise ValueError(
                f"Implementation '{name}' not found. Available: {available}"
            )

        implementation_class = self._implementations[name]
        config = self._configurations.get(name, {})

        # Merge factory config with runtime kwargs
        final_config = {**config, **kwargs}

        logger.debug(
            f"Creating {implementation_class.__name__} with config: {final_config}"
        )

        try:
            return implementation_class(**final_config)
        except Exception as e:
            logger.error(f"Failed to create {implementation_class.__name__}: {e}")
            raise

    def list_implementations(self) -> Dict[str, Type[P]]:
        """List all registered implementations."""
        return self._implementations.copy()

    def get_default_implementation(self) -> Optional[str]:
        """Get the default implementation name."""
        return self._default_implementation


class NotificationServiceFactory(ServiceFactory[NotificationServiceProtocol]):
    """Factory for creating notification services."""
    
    def __init__(self) -> None:
        super().__init__()
        self._register_default_implementations()
    
    def _register_default_implementations(self) -> None:
        """Register default notification service implementations."""
        from borgitory.services.notifications.pushover_service import PushoverService

        self.register_implementation("pushover", PushoverService, set_as_default=True)

        # Future implementations can be registered here:
        # self.register_implementation("email", EmailNotificationService)
        # self.register_implementation("slack", SlackNotificationService)

    def create_notification_service(
        self, provider: str = "pushover", **config: Any
    ) -> NotificationServiceProtocol:
        """Create a notification service for the specified provider."""
        return self.create_service(provider, **config)


class CommandRunnerFactory(ServiceFactory[CommandRunnerProtocol]):
    """Factory for creating command runner services."""

    def __init__(self) -> None:
        super().__init__()
        self._register_default_implementations()

    def _register_default_implementations(self) -> None:
        """Register default command runner implementations."""
        from borgitory.services.simple_command_runner import SimpleCommandRunner

        self.register_implementation("simple", SimpleCommandRunner, set_as_default=True)

        # Future implementations:
        # self.register_implementation("async", AsyncCommandRunner)
        # self.register_implementation("distributed", DistributedCommandRunner)

    def create_command_runner(
        self, runner_type: str = "simple", **config: Any
    ) -> CommandRunnerProtocol:
        """Create a command runner of the specified type."""
        return self.create_service(runner_type, **config)


class BackupServiceFactory(ServiceFactory[BackupServiceProtocol]):
    """Factory for creating backup services."""

    def __init__(self) -> None:
        super().__init__()
        self._register_default_implementations()

    def _register_default_implementations(self) -> None:
        """Register default backup service implementations."""

        # Note: BorgService requires dependencies, so we'll use a factory function
        def create_borg_service(**kwargs: Any) -> BackupServiceProtocol:
            from borgitory.services.borg_service import BorgService
            from borgitory.dependencies import (
                get_simple_command_runner,
                get_volume_service,
                get_job_manager_dependency,
            )

            # Use provided dependencies or defaults
            command_runner = kwargs.get("command_runner", get_simple_command_runner())
            volume_service = kwargs.get("volume_service", get_volume_service())
            job_manager = kwargs.get("job_manager", get_job_manager_dependency())

            return BorgService(  # type: ignore[return-value]
                command_runner=command_runner,
                volume_service=volume_service,
                job_manager=job_manager,
            )

        self.register_implementation("borg", create_borg_service, set_as_default=True)  # type: ignore[arg-type]

        # Future implementations:
        # self.register_implementation("restic", ResticService)
        # self.register_implementation("duplicity", DuplicityService)

    def create_backup_service(
        self, backup_type: str = "borg", **config: Any
    ) -> BackupServiceProtocol:
        """Create a backup service of the specified type."""
        return self.create_service(backup_type, **config)


class ServiceRegistry:
    """Central registry for all service factories."""

    def __init__(self) -> None:
        self._factories: Dict[str, "ServiceFactory[Any]"] = {}
        self._initialize_default_factories()

    def _initialize_default_factories(self) -> None:
        """Initialize default service factories."""
        self.register_factory("notifications", NotificationServiceFactory())
        self.register_factory("command_runners", CommandRunnerFactory())
        self.register_factory("backup_services", BackupServiceFactory())

    def register_factory(self, name: str, factory: "ServiceFactory[Any]") -> None:
        """Register a service factory."""
        self._factories[name] = factory
        logger.info(f"Registered factory '{name}'")

    def get_factory(self, name: str) -> "ServiceFactory[Any]":
        """Get a service factory by name."""
        if name not in self._factories:
            available = list(self._factories.keys())
            raise ValueError(f"Factory '{name}' not found. Available: {available}")
        return self._factories[name]

    def list_factories(self) -> Dict[str, "ServiceFactory[Any]"]:
        """List all registered factories."""
        return self._factories.copy()

    # Convenience methods for common factories
    def get_notification_factory(self) -> NotificationServiceFactory:
        """Get the notification service factory."""
        return self.get_factory("notifications")  # type: ignore[return-value]

    def get_command_runner_factory(self) -> CommandRunnerFactory:
        """Get the command runner factory."""
        return self.get_factory("command_runners")  # type: ignore[return-value]

    def get_backup_service_factory(self) -> BackupServiceFactory:
        """Get the backup service factory."""
        return self.get_factory("backup_services")  # type: ignore[return-value]


# Global service registry instance
_service_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry instance."""
    global _service_registry
    if _service_registry is None:
        _service_registry = ServiceRegistry()
    return _service_registry


# Convenience functions for common operations
def create_notification_service(
    provider: str = "pushover", **config: Any
) -> NotificationServiceProtocol:
    """Create a notification service using the factory."""
    registry = get_service_registry()
    factory = registry.get_notification_factory()
    return factory.create_notification_service(provider, **config)


def create_command_runner(
    runner_type: str = "simple", **config: Any
) -> CommandRunnerProtocol:
    """Create a command runner using the factory."""
    registry = get_service_registry()
    factory = registry.get_command_runner_factory()
    return factory.create_command_runner(runner_type, **config)


def create_backup_service(
    backup_type: str = "borg", **config: Any
) -> BackupServiceProtocol:
    """Create a backup service using the factory."""
    registry = get_service_registry()
    factory = registry.get_backup_service_factory()
    return factory.create_backup_service(backup_type, **config)
