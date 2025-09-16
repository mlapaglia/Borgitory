import json
import logging
from datetime import datetime, UTC
from typing import List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.database import CloudSyncConfig
from models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
)
from services.rclone_service import RcloneService
from services.cloud_providers.registry import (
    get_storage_class,
)
from services.cloud_providers import StorageFactory, EncryptionService

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
                return storage_class.get_sensitive_fields(None)
            except TypeError:
                # It's an instance method, so we need to create a temporary instance
                # Since we only need the get_sensitive_fields method, we can pass None
                # for both config and rclone_service - storage classes should handle this
                try:
                    temp_storage = storage_class(None, None)
                    return temp_storage.get_sensitive_fields()
                except Exception as e:
                    logger.warning(
                        f"Failed to create temp storage instance for {provider}: {e}"
                    )
                    # If we can't create an instance, try to inspect the method
                    # or return empty list - no hardcoded fallbacks
                    return []

        logger.warning(
            f"Provider '{provider}' storage class has no get_sensitive_fields method"
        )
        return []

    except Exception as e:
        logger.warning(f"Error getting sensitive fields for provider '{provider}': {e}")
        return []


class CloudSyncService:
    """Service class for cloud sync configuration operations."""

    def __init__(
        self,
        db: Session,
        rclone_service: RcloneService = None,
        storage_factory: StorageFactory = None,
        encryption_service: EncryptionService = None,
        provider_registry=None,
    ):
        self.db = db
        self._rclone_service = rclone_service or RcloneService()
        self._storage_factory = storage_factory or StorageFactory(self._rclone_service)
        self._encryption_service = encryption_service or EncryptionService()
        self._provider_registry = provider_registry

    def create_cloud_sync_config(
        self, config: CloudSyncConfigCreate
    ) -> CloudSyncConfig:
        """Create a new cloud sync configuration using the new provider pattern."""
        import json

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

        if not self._provider_registry:
            raise ValueError("Provider registry is required but not provided")

        supported_providers = self._provider_registry.get_supported_providers()
        if config.provider not in supported_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {config.provider}. Available providers: {', '.join(sorted(supported_providers))}",
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

        db_config = CloudSyncConfig(
            name=config.name,
            provider=config.provider,
            provider_config=json.dumps(encrypted_config),
            path_prefix=config.path_prefix or "",
        )

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
        import json

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
                config_update.provider if config_update.provider else config.provider
            )
            try:
                rclone_service = RcloneService()
                storage_factory = StorageFactory(rclone_service)
                storage = storage_factory.create_storage(
                    provider, config_update.provider_config
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid provider configuration: {str(e)}"
                )

            encryption_service = EncryptionService()
            sensitive_fields = storage.get_sensitive_fields()
            encrypted_config = encryption_service.encrypt_sensitive_fields(
                config_update.provider_config, sensitive_fields
            )

            config.provider_config = json.dumps(encrypted_config)

        config.updated_at = datetime.now(UTC)
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
        config.updated_at = datetime.now(UTC)
        self.db.commit()
        return config

    def disable_cloud_sync_config(self, config_id: int) -> CloudSyncConfig:
        """Disable a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)
        config.enabled = False
        config.updated_at = datetime.now(UTC)
        self.db.commit()
        return config

    async def test_cloud_sync_config(
        self,
        config_id: int,
        rclone: RcloneService,
        encryption_service=None,
        storage_factory=None,
    ) -> dict:
        """Test a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)

        provider_config = json.loads(config.provider_config)

        if encryption_service is None:
            encryption_service = self._encryption_service
        if storage_factory is None:
            storage_factory = self._storage_factory

        sensitive_fields = _get_sensitive_fields_for_provider(config.provider)

        decrypted_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

        storage_factory.create_storage(config.provider, decrypted_config)

        if config.provider == "s3":
            result = await rclone.test_s3_connection(
                access_key_id=decrypted_config["access_key"],
                secret_access_key=decrypted_config["secret_key"],
                bucket_name=decrypted_config["bucket_name"],
            )

        elif config.provider == "sftp":
            result = await rclone.test_sftp_connection(
                host=decrypted_config["host"],
                username=decrypted_config["username"],
                remote_path=decrypted_config["remote_path"],
                port=decrypted_config.get("port", 22),
                password=decrypted_config.get("password"),
                private_key=decrypted_config.get("private_key"),
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider for testing: {config.provider}",
            )

        return result

    def get_decrypted_config_for_editing(
        self, config_id: int, encryption_service, storage_factory
    ) -> dict:
        """Get decrypted configuration for editing in forms."""
        config = self.get_cloud_sync_config_by_id(config_id)

        provider_config = json.loads(config.provider_config)

        sensitive_fields = _get_sensitive_fields_for_provider(config.provider)

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
