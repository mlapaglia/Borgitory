"""
Protocol-based service factory for creating services dynamically.

This factory enables runtime service creation based on protocols,
supporting different implementations and configurations.
"""

from typing import (
    Type,
    Dict,
    Optional,
    TypeVar,
    Generic,
    Union,
    Callable,
    Any,
    TYPE_CHECKING,
)
from abc import ABC
import logging

from borgitory.protocols.notification_protocols import NotificationServiceProtocol
from borgitory.protocols.cloud_protocols import CloudSyncConfigServiceProtocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from borgitory.services.encryption_service import EncryptionService
    from borgitory.services.cloud_providers import StorageFactory
    from borgitory.services.rclone_service import RcloneService

logger = logging.getLogger(__name__)

# Define TypeVar here - this was missing!
P = TypeVar("P")

# Union type for implementations
ImplementationType = Union[Type[P], Callable[..., P]]


class ServiceFactory(Generic[P], ABC):
    """Base factory for creating protocol-compliant services."""

    def __init__(self) -> None:
        self._implementations: Dict[str, ImplementationType[P]] = {}
        self._configurations: Dict[str, Dict[str, Any]] = {}
        self._default_implementation: Optional[str] = None

    def register_implementation(
        self,
        name: str,
        implementation: ImplementationType[P],
        config: Optional[Dict[str, Any]] = None,
        set_as_default: bool = False,
    ) -> None:
        """Register a service implementation."""
        self._implementations[name] = implementation
        if config:
            self._configurations[name] = config

        if set_as_default or not self._default_implementation:
            self._default_implementation = name

        # Handle both classes and functions for logging
        impl_name = getattr(implementation, "__name__", str(implementation))
        logger.info(f"Registered {impl_name} as '{name}' implementation")

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

        implementation = self._implementations[name]
        config = self._configurations.get(name, {})

        # Merge factory config with runtime kwargs
        final_config = {**config, **kwargs}

        impl_name = getattr(implementation, "__name__", str(implementation))
        logger.debug(f"Creating {impl_name} with config: {final_config}")

        try:
            return implementation(**final_config)
        except Exception as e:
            logger.error(f"Failed to create {impl_name}: {e}")
            raise

    def list_implementations(self) -> Dict[str, ImplementationType[P]]:
        """List all registered implementations."""
        return self._implementations.copy()

    def get_default_implementation(self) -> Optional[str]:
        """Get the default implementation name."""
        return self._default_implementation


class NotificationServiceFactory(ServiceFactory[NotificationServiceProtocol]):
    """Factory for creating notification services with proper dependency injection."""

    def __init__(self, http_client: Any) -> None:
        super().__init__()
        # Inject dependencies instead of using service locator
        self._http_client = http_client
        self._register_default_implementations()

    def _register_default_implementations(self) -> None:
        """Register default notification service implementations."""
        from borgitory.services.notifications.service import (
            NotificationService,
            NotificationProviderFactory,
        )

        def create_notification_service(
            encryption_service: Optional[Any] = None,
        ) -> NotificationServiceProtocol:
            """Factory function to create NotificationService."""
            provider_factory = NotificationProviderFactory(
                http_client=self._http_client
            )
            return NotificationService(
                provider_factory=provider_factory, encryption_service=encryption_service
            )

        self.register_implementation(
            "provider_based", create_notification_service, set_as_default=True
        )

    def create_notification_service(
        self,
        service_type: str = "provider_based",
        encryption_service: Optional["EncryptionService"] = None,
    ) -> NotificationServiceProtocol:
        """Create a notification service."""
        return self.create_service(service_type, encryption_service=encryption_service)


class CloudProviderServiceFactory(ServiceFactory[CloudSyncConfigServiceProtocol]):
    """Factory for creating cloud provider services with proper dependency injection."""

    def __init__(
        self,
        rclone_service: "RcloneService",
        storage_factory: "StorageFactory",
        encryption_service: "EncryptionService",
        metadata_func: Callable[..., Any],
    ) -> None:
        super().__init__()
        # Inject dependencies instead of using service locator
        self._rclone_service = rclone_service
        self._storage_factory = storage_factory
        self._encryption_service = encryption_service
        self._metadata_func = metadata_func
        self._register_default_implementations()

    def _register_default_implementations(self) -> None:
        """Register default cloud sync service implementations."""

        def create_cloud_sync_service(db: "Session") -> CloudSyncConfigServiceProtocol:
            """Factory function to create CloudSyncConfigService."""
            # Import here to avoid circular dependencies
            from borgitory.services.cloud_sync_service import CloudSyncConfigService

            # Use injected dependencies - no more service locator!
            return CloudSyncConfigService(
                db=db,
                rclone_service=self._rclone_service,
                storage_factory=self._storage_factory,
                encryption_service=self._encryption_service,
                get_metadata_func=self._metadata_func,
            )

        self.register_implementation(
            "default", create_cloud_sync_service, set_as_default=True
        )

    def create_cloud_sync_service(
        self, db: "Session", service_type: str = "default"
    ) -> CloudSyncConfigServiceProtocol:
        """Create a cloud sync service."""
        return self.create_service(service_type, db=db)
