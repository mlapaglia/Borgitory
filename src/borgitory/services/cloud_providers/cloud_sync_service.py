"""
Cloud sync service layer.

This module provides the high-level service interface for cloud sync operations,
including configuration validation, storage creation, and encryption handling.
"""

import inspect
import json
import logging
from typing import (
    Dict,
    List,
    Callable,
    Optional,
    cast,
    get_type_hints,
    Union,
    get_origin,
    get_args,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.services.rclone_service import RcloneService

from .types import CloudSyncConfig, SyncResult
from .storage import CloudStorage
from .registry import ProviderRegistry
from .orchestration import CloudSyncer, LoggingSyncEventHandler
from borgitory.services.encryption_service import EncryptionService
from borgitory.custom_types import ConfigDict

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates cloud storage configurations"""

    def __init__(self, registry: Optional["ProviderRegistry"] = None) -> None:
        """
        Initialize validator with optional registry injection.

        Args:
            registry: Provider registry instance. If None, uses global registry.
        """
        if registry is not None:
            self._registry = registry
        else:
            # Fallback to global registry for backward compatibility
            from .registry import get_registry

            self._registry = get_registry()

    def validate_config(self, provider: str, config: ConfigDict) -> object:
        """
        Validate configuration for a specific provider.

        Args:
            provider: Provider name (e.g., s3, sftp, smb)
            config: Configuration dictionary

        Returns:
            Validated configuration object

        Raises:
            ValueError: If configuration is invalid or provider is unknown
        """
        config_class = self._registry.get_config_class(provider)
        if config_class is None:
            supported = self._registry.get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        # Filter out None values for the config class constructor
        filtered_config = {k: v for k, v in config.items() if v is not None}
        return config_class(**filtered_config)


class StorageFactory:
    """Factory for creating cloud storage instances with automatic dependency injection"""

    def __init__(
        self,
        rclone_service: Optional[RcloneService] = None,
        command_executor: Optional[object] = None,
        file_service: Optional[object] = None,
        registry: Optional["ProviderRegistry"] = None,
    ) -> None:
        """
        Initialize storage factory with available dependencies.

        Args:
            rclone_service: Rclone service for I/O operations (optional for DI)
            command_executor: Command executor for running external commands (optional for DI)
            file_service: File service for file operations (optional for DI)
            registry: Provider registry instance (optional for DI)
        """
        if registry is not None:
            self._registry = registry
        else:
            from .registry import get_registry

            self._registry = get_registry()

        self._validator = ConfigValidator(registry=self._registry)
        self._dependencies = {
            "rclone_service": rclone_service,
            "command_executor": command_executor,
            "file_service": file_service,
        }

    def create_storage(self, provider: str, config: ConfigDict) -> CloudStorage:
        """
        Create a cloud storage instance with automatic dependency injection.

        Args:
            provider: Provider name (e.g., s3, sftp, smb)
            config: Configuration dictionary

        Returns:
            CloudStorage instance

        Raises:
            ValueError: If provider is unknown or config is invalid
        """
        validated_config = self._validator.validate_config(provider, config)

        storage_class = self._registry.get_storage_class(provider)
        if storage_class is None:
            supported = self._registry.get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        # Create storage instance with automatic dependency injection
        return self._create_storage_with_dependencies(storage_class, validated_config)

    def _create_storage_with_dependencies(
        self, storage_class: type, validated_config: object
    ) -> CloudStorage:
        """
        Automatically inject dependencies based on constructor signature.

        Uses inspection to determine what dependencies the storage provider needs
        and injects available ones, with type checking support.

        **DI CHECK**: Following the exact same pattern as NotificationProviderFactory
        """
        try:
            # Get constructor signature
            sig = inspect.signature(storage_class.__init__)  # type: ignore[misc]

            # Get type hints for additional validation
            try:
                type_hints = get_type_hints(storage_class.__init__)  # type: ignore[misc]
            except (NameError, AttributeError):
                # Some storage providers might not have complete type hints
                type_hints = {}

            # Build kwargs with available dependencies
            kwargs: Dict[str, object] = {
                "config": validated_config
            }  # Always pass config

            for param_name, param in sig.parameters.items():
                if param_name in ["self", "config"]:
                    continue

                # Check if we have this dependency available
                if (
                    param_name in self._dependencies
                    and self._dependencies[param_name] is not None
                ):
                    dependency_value = self._dependencies[param_name]

                    # Optional: Type checking if type hints are available
                    if param_name in type_hints:
                        expected_type = type_hints[param_name]

                        # Handle Optional types (Union[SomeType, None])
                        origin = get_origin(expected_type)
                        if origin is Union:
                            args = get_args(expected_type)
                            # Check if this is Optional[T] (Union[T, None])
                            if len(args) == 2 and type(None) in args:
                                # Extract the non-None type
                                expected_type = (
                                    args[0] if args[1] is type(None) else args[1]
                                )

                        # Basic type validation (can be enhanced)
                        try:
                            if not isinstance(dependency_value, expected_type):
                                logger.warning(
                                    f"Type mismatch for {param_name}: expected {expected_type}, "
                                    f"got {type(dependency_value)}. Injecting anyway."
                                )
                        except TypeError:
                            # Some types might not work with isinstance (e.g., generics)
                            logger.debug(
                                f"Cannot validate type for {param_name}, injecting anyway"
                            )

                    kwargs[param_name] = dependency_value
                    logger.debug(
                        f"Injecting {param_name} into {storage_class.__name__}"
                    )

                elif param.default is not param.empty:
                    # Parameter has default value, skip injection
                    logger.debug(f"Skipping {param_name} (has default value)")
                    continue
                else:
                    # Required parameter we don't have
                    logger.warning(
                        f"Required parameter '{param_name}' for {storage_class.__name__} "
                        f"not available in dependencies"
                    )

            return cast(CloudStorage, storage_class(**kwargs))

        except Exception as e:
            logger.error(
                f"Failed to create storage {storage_class.__name__} with DI: {e}"
            )
            raise ValueError(
                f"Could not create storage {storage_class.__name__}: {e}"
            ) from e

    def get_supported_providers(self) -> List[str]:
        """Get list of supported provider names."""
        return self._registry.get_supported_providers()

    def get_sensitive_fields(self, provider: str) -> List[str]:
        """
        Get list of sensitive fields for a provider without requiring a config instance.

        This uses a static mapping of known sensitive fields for each provider.
        This avoids the circular dependency of needing a valid config to decrypt
        the config.

        Args:
            provider: Provider name (e.g., s3, sftp, smb)

        Returns:
            List of sensitive field names

        Raises:
            ValueError: If provider is unknown
        """
        # Verify the provider exists in registry
        storage_class = self._registry.get_storage_class(provider)
        if storage_class is None:
            supported = self._registry.get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        # Use static mapping of sensitive fields
        mapping = {
            "s3": ["access_key", "secret_key"],
            "sftp": ["password", "private_key"],
            "smb": ["pass"],
        }
        return mapping.get(provider, [])


class CloudSyncService:
    """
    High-level service for cloud sync operations.

    This service coordinates all the components to provide a clean,
    easy-to-test interface for cloud sync functionality.
    """

    def __init__(
        self,
        storage_factory: StorageFactory,
        encryption_service: Optional[EncryptionService] = None,
    ) -> None:
        """
        Initialize cloud sync service.

        Args:
            storage_factory: Factory for creating storage instances
            encryption_service: Service for handling encryption (optional)
        """
        self._storage_factory = storage_factory
        self._encryption_service = encryption_service or EncryptionService()

    async def execute_sync(
        self,
        config: CloudSyncConfig,
        repository_path: str,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> SyncResult:
        """
        Execute a cloud sync operation.

        This is the main entry point for cloud sync operations.
        It handles all the complexity internally and returns a simple result.

        Args:
            config: Cloud sync configuration
            repository_path: Path to the repository to sync
            output_callback: Optional callback for real-time output

        Returns:
            SyncResult indicating success/failure and details
        """
        try:
            storage = self._storage_factory.create_storage(
                config.provider, config.config
            )

            event_handler = LoggingSyncEventHandler(logger, output_callback)

            syncer = CloudSyncer(storage, event_handler)

            return await syncer.sync_repository(repository_path, config.path_prefix)

        except Exception as e:
            error_msg = f"Failed to execute sync: {str(e)}"
            logger.error(error_msg)
            if output_callback:
                output_callback(error_msg)
            return SyncResult.error_result(error_msg)

    async def execute_sync_from_db(
        self,
        config_id: int,
        repository_path: str,
        db: "AsyncSession",
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> SyncResult:
        """
        Execute a cloud sync operation by loading config from database.

        This method handles loading the config from the database, decrypting
        sensitive fields, and then executing the sync.

        Args:
            config_id: Database ID of the cloud sync configuration
            repository_path: Path to the repository to sync
            db: Database session for loading config
            output_callback: Optional callback for real-time output

        Returns:
            SyncResult indicating success/failure and details
        """
        try:
            from borgitory.models.database import CloudSyncConfig as DBCloudSyncConfig
            from sqlalchemy import select

            if output_callback:
                output_callback("Loading cloud sync configuration...")

            result = await db.execute(
                select(DBCloudSyncConfig).where(DBCloudSyncConfig.id == config_id)
            )
            db_config = result.scalar_one_or_none()

            if not db_config:
                error_msg = f"Cloud sync configuration {config_id} not found"
                logger.error(error_msg)
                if output_callback:
                    output_callback(error_msg)
                return SyncResult.error_result(error_msg)

            if not db_config.enabled:
                info_msg = "Cloud sync configuration is disabled - skipping"
                logger.info(info_msg)
                if output_callback:
                    output_callback(info_msg)
                return SyncResult.success_result()

            if not db_config.provider_config:
                error_msg = f"Cloud sync configuration '{db_config.name}' has no provider_config"
                logger.error(error_msg)
                if output_callback:
                    output_callback(error_msg)
                return SyncResult.error_result(error_msg)

            try:
                encrypted_config = json.loads(db_config.provider_config)
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON in provider_config: {e}"
                logger.error(error_msg)
                if output_callback:
                    output_callback(error_msg)
                return SyncResult.error_result(error_msg)

            # Get sensitive fields without creating a storage instance (avoids validation errors with encrypted config)
            sensitive_fields = self._storage_factory.get_sensitive_fields(
                db_config.provider
            )

            # Decrypt the config before validation
            decrypted_config = self._encryption_service.decrypt_sensitive_fields(
                encrypted_config, sensitive_fields
            )

            if db_config.path_prefix:
                decrypted_config["path_prefix"] = db_config.path_prefix

            if output_callback:
                output_callback(
                    f"Syncing to {db_config.name} ({db_config.provider.upper()})"
                )

            sync_config = CloudSyncConfig(
                provider=db_config.provider,
                config=decrypted_config,
                path_prefix=db_config.path_prefix or "",
                name=db_config.name,
            )

            return await self.execute_sync(
                sync_config, repository_path, output_callback
            )

        except Exception as e:
            error_msg = f"Failed to execute sync from database: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if output_callback:
                output_callback(error_msg)
            return SyncResult.error_result(error_msg)

    async def test_connection(self, config: CloudSyncConfig) -> bool:
        """
        Test connection to cloud storage.

        Args:
            config: Cloud sync configuration

        Returns:
            True if connection successful, False otherwise
        """
        try:
            storage = self._storage_factory.create_storage(
                config.provider, config.config
            )
            return await storage.test_connection()

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False

    def get_connection_info(self, config: CloudSyncConfig) -> str:
        """
        Get connection information for display.

        Args:
            config: Cloud sync configuration

        Returns:
            String representation of connection info
        """
        try:
            storage = self._storage_factory.create_storage(
                config.provider, config.config
            )
            return str(storage.get_connection_info())

        except Exception as e:
            return f"Error getting connection info: {str(e)}"

    def prepare_config_for_storage(self, provider: str, config: ConfigDict) -> str:
        """
        Prepare configuration for database storage by encrypting sensitive fields.

        Args:
            provider: Provider name
            config: Configuration dictionary

        Returns:
            JSON string with encrypted sensitive fields
        """

        temp_storage = self._storage_factory.create_storage(provider, config)
        sensitive_fields = temp_storage.get_sensitive_fields()

        encrypted_config = self._encryption_service.encrypt_sensitive_fields(
            config, sensitive_fields
        )

        return json.dumps(encrypted_config)

    def load_config_from_storage(self, provider: str, stored_config: str) -> ConfigDict:
        """
        Load configuration from database storage by decrypting sensitive fields.

        Args:
            provider: Provider name
            stored_config: JSON string from database

        Returns:
            Configuration dictionary with decrypted sensitive fields
        """
        config = json.loads(stored_config)

        temp_storage = self._storage_factory.create_storage(provider, config)
        sensitive_fields = temp_storage.get_sensitive_fields()

        return self._encryption_service.decrypt_sensitive_fields(
            config, sensitive_fields
        )
