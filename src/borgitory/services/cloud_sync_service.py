import inspect
import json
import logging
from borgitory.utils.datetime_utils import now_utc
from typing import Any, List, Dict, Callable, cast, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.services.cloud_providers.registry import ProviderMetadata
from fastapi import HTTPException
from sqlalchemy.orm import Session

from borgitory.models.database import CloudSyncConfig
from borgitory.models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
)
from borgitory.services.rclone_service import RcloneService
from borgitory.services.cloud_providers.registry import (
    get_storage_class,
)
from borgitory.services.cloud_providers import StorageFactory
from borgitory.services.encryption_service import EncryptionService

logger = logging.getLogger(__name__)


def _get_sensitive_fields_for_provider(provider: str) -> list[str]:
    """Get sensitive fields for a provider using the registry system."""
    storage_class = get_storage_class(provider)
    if storage_class is None:
        logger.warning(
            f"Unknown provider '{provider}', returning empty sensitive fields list"
        )
        return []

    # Create a temporary instance to get sensitive fields
    # We need to pass None for config and rclone_service since we only need the method
    try:
        if hasattr(storage_class, "get_sensitive_fields"):
            # Try to call it as a static method first
            try:
                result = storage_class.get_sensitive_fields(None)
                return cast(list[str], result)
            except TypeError:
                # It's an instance method, so we need to create a temporary instance
                # Since we only need the get_sensitive_fields method, we can pass None
                # for both config and rclone_service - storage classes should handle this
                try:
                    temp_storage = storage_class(None, None)
                    result = temp_storage.get_sensitive_fields()
                    return cast(list[str], result)
                except Exception as e:
                    logger.warning(
                        f"Failed to create temp storage instance for {provider}: {e}"
                    )

                    return []

        logger.warning(
            f"Provider '{provider}' storage class has no get_sensitive_fields method"
        )
        return []

    except Exception as e:
        logger.warning(f"Error getting sensitive fields for provider '{provider}': {e}")
        return []


class CloudSyncConfigService:
    """Service class for cloud sync configuration management (CRUD operations)."""

    def __init__(
        self,
        db: Session,
        rclone_service: RcloneService,
        storage_factory: StorageFactory,
        encryption_service: EncryptionService,
        get_metadata_func: Callable[[str], Optional["ProviderMetadata"]],
    ):
        self.db = db
        self._rclone_service = rclone_service
        self._storage_factory = storage_factory
        self._encryption_service = encryption_service
        self._get_metadata = get_metadata_func

    def create_cloud_sync_config(
        self, config: CloudSyncConfigCreate
    ) -> CloudSyncConfig:
        """Create a new cloud sync configuration using the new provider pattern."""

        existing = (
            self.db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.name == config.name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Cloud sync configuration with name '{config.name}' already exists",
            )

        # Validate provider exists by checking if we can get its metadata
        metadata = self._get_metadata(config.provider)
        if not metadata:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {config.provider}",
            )

        try:
            storage = self._storage_factory.create_storage(
                config.provider, config.provider_config
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid provider configuration: {str(e)}"
            )

        sensitive_fields = storage.get_sensitive_fields()
        encrypted_config = self._encryption_service.encrypt_sensitive_fields(
            config.provider_config, sensitive_fields
        )

        db_config = CloudSyncConfig()
        db_config.name = config.name
        db_config.provider = config.provider
        db_config.provider_config = json.dumps(encrypted_config)
        db_config.path_prefix = config.path_prefix or ""

        self.db.add(db_config)
        self.db.commit()
        self.db.refresh(db_config)

        return db_config

    def get_cloud_sync_configs(self) -> List[CloudSyncConfig]:
        """Get all cloud sync configurations."""
        return self.db.query(CloudSyncConfig).all()

    def get_cloud_sync_config_by_id(self, config_id: int) -> CloudSyncConfig:
        """Get cloud sync configuration by ID."""
        config = (
            self.db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == config_id)
            .first()
        )
        if not config:
            raise HTTPException(
                status_code=404, detail="Cloud sync configuration not found"
            )
        return config

    def update_cloud_sync_config(
        self, config_id: int, config_update: CloudSyncConfigUpdate
    ) -> CloudSyncConfig:
        """Update a cloud sync configuration."""

        config = self.get_cloud_sync_config_by_id(config_id)

        if config_update.name and config_update.name != config.name:
            existing = (
                self.db.query(CloudSyncConfig)
                .filter(
                    CloudSyncConfig.name == config_update.name,
                    CloudSyncConfig.id != config_id,
                )
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cloud sync configuration with name '{config_update.name}' already exists",
                )

        if config_update.name is not None:
            config.name = config_update.name
        if config_update.provider is not None:
            config.provider = config_update.provider
        if config_update.path_prefix is not None:
            config.path_prefix = config_update.path_prefix
        if config_update.enabled is not None:
            config.enabled = config_update.enabled

        if config_update.provider_config is not None:
            provider = (
                config_update.provider
                if config_update.provider
                else str(config.provider)
            )
            try:
                storage = self._storage_factory.create_storage(
                    provider, config_update.provider_config
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid provider configuration: {str(e)}"
                )

            sensitive_fields = storage.get_sensitive_fields()
            encrypted_config = self._encryption_service.encrypt_sensitive_fields(
                config_update.provider_config, sensitive_fields
            )

            config.provider_config = json.dumps(encrypted_config)

        config.updated_at = now_utc()
        self.db.commit()
        self.db.refresh(config)

        return config

    def delete_cloud_sync_config(self, config_id: int) -> None:
        """Delete a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)
        self.db.delete(config)
        self.db.commit()

    def enable_cloud_sync_config(self, config_id: int) -> CloudSyncConfig:
        """Enable a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)
        config.enabled = True
        config.updated_at = now_utc()
        self.db.commit()
        return config

    def disable_cloud_sync_config(self, config_id: int) -> CloudSyncConfig:
        """Disable a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)
        config.enabled = False
        config.updated_at = now_utc()
        self.db.commit()
        return config

    async def test_cloud_sync_config(
        self,
        config_id: int,
        rclone: RcloneService,
        encryption_service: EncryptionService,
        storage_factory: StorageFactory,
    ) -> Dict[str, Any]:
        """Test a cloud sync configuration using dynamic provider registry."""
        logger.info(f"Starting test for cloud sync config {config_id}")

        config = self.get_cloud_sync_config_by_id(config_id)
        logger.info(
            f"Config {config_id}: provider={config.provider}, name={config.name}"
        )

        provider_config = json.loads(str(config.provider_config))

        sensitive_fields = _get_sensitive_fields_for_provider(str(config.provider))

        decrypted_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

        storage_factory.create_storage(str(config.provider), decrypted_config)

        # Get provider metadata and rclone mapping using injected dependency
        metadata = self._get_metadata(str(config.provider))
        if not metadata or not metadata.rclone_mapping:
            logger.error(
                f"Provider '{config.provider}' not registered or missing rclone mapping"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{config.provider}' not registered or missing rclone mapping",
            )

        mapping = metadata.rclone_mapping
        test_method_name = mapping.test_method
        logger.info(f"Using test method: {test_method_name}")

        # Check if rclone service has the test method
        if not hasattr(rclone, test_method_name):
            logger.error(f"Rclone service missing test method: {test_method_name}")
            raise HTTPException(
                status_code=500,
                detail=f"Rclone service missing test method: {test_method_name}",
            )

        # Build parameters for the test method using parameter mapping
        test_params: Dict[str, Union[str, int, float, bool, None]] = {}
        logger.info(f"Decrypted config fields: {list(decrypted_config.keys())}")
        logger.info(f"Parameter mapping: {mapping.parameter_mapping}")

        for config_field, rclone_param in mapping.parameter_mapping.items():
            if config_field in decrypted_config:
                test_params[rclone_param] = decrypted_config[config_field]
                logger.info(f"Mapped {config_field} -> {rclone_param}")
            else:
                logger.info(
                    f"Config field '{config_field}' not found in decrypted config"
                )

        # Add optional parameters with defaults if not already set
        if mapping.optional_params:
            for param, default_value in mapping.optional_params.items():
                if param not in test_params:
                    if (
                        isinstance(default_value, (str, int, float, bool))
                        or default_value is None
                    ):
                        test_params[param] = default_value
                    else:
                        test_params[param] = str(default_value)

        logger.info(
            f"Built test params: {list(test_params.keys())}"
        )  # Don't log values for security

        # Get the test method and filter parameters to match method signature
        test_method = getattr(rclone, test_method_name)

        # Filter parameters to only include those supported by the test method
        method_signature = inspect.signature(test_method)
        filtered_params = {
            param: value
            for param, value in test_params.items()
            if param in method_signature.parameters
        }

        logger.info(
            f"Filtered params for {test_method_name}: {list(filtered_params.keys())}"
        )

        try:
            result = await test_method(**filtered_params)
            logger.info(f"Test method result: {result}")
            return cast(Dict[str, Any], result)
        except Exception as e:
            logger.error(f"Error calling {test_method_name}: {e}", exc_info=True)
            raise

    def get_decrypted_config_for_editing(
        self,
        config_id: int,
        encryption_service: EncryptionService,
        storage_factory: StorageFactory,
    ) -> Dict[str, Any]:
        """Get decrypted configuration for editing in forms."""
        config = self.get_cloud_sync_config_by_id(config_id)

        provider_config = json.loads(str(config.provider_config))

        sensitive_fields = _get_sensitive_fields_for_provider(str(config.provider))

        decrypted_provider_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

        decrypted_config = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "path_prefix": config.path_prefix,
            "enabled": config.enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

        decrypted_config.update(decrypted_provider_config)

        return decrypted_config
