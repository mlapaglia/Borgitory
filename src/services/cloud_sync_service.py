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

logger = logging.getLogger(__name__)


class CloudSyncService:
    """Service class for cloud sync configuration operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_cloud_sync_config(
        self, config: CloudSyncConfigCreate
    ) -> CloudSyncConfig:
        """Create a new cloud sync configuration using the new provider pattern."""
        from services.cloud_providers import StorageFactory, EncryptionService
        from services.rclone_service import RcloneService
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

        # Validate provider exists and configuration is valid
        supported_providers = ["s3", "sftp"]
        if config.provider.value not in supported_providers:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {config.provider}. Available providers: {', '.join(supported_providers)}",
            )

        # Create storage instance to validate configuration (this will raise validation errors if invalid)
        try:
            rclone_service = RcloneService()
            storage_factory = StorageFactory(rclone_service)
            storage = storage_factory.create_storage(
                config.provider.value, config.provider_config
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid provider configuration: {str(e)}"
            )

        # Encrypt sensitive fields in the configuration
        encryption_service = EncryptionService()
        sensitive_fields = storage.get_sensitive_fields()
        encrypted_config = encryption_service.encrypt_sensitive_fields(
            config.provider_config, sensitive_fields
        )

        # Create database record
        db_config = CloudSyncConfig(
            name=config.name,
            provider=config.provider.value,
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
        from services.cloud_providers import StorageFactory, EncryptionService
        from services.rclone_service import RcloneService
        import json

        config = self.get_cloud_sync_config_by_id(config_id)

        # Check for duplicate name
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

        # Update basic fields
        if config_update.name is not None:
            config.name = config_update.name
        if config_update.provider is not None:
            config.provider = config_update.provider.value
        if config_update.path_prefix is not None:
            config.path_prefix = config_update.path_prefix
        if config_update.enabled is not None:
            config.enabled = config_update.enabled

        # Update provider_config if provided
        if config_update.provider_config is not None:
            # Validate the new configuration
            provider = (
                config_update.provider.value
                if config_update.provider
                else config.provider
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

            # Encrypt sensitive fields in the new configuration
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

        # Parse JSON configuration
        import json

        provider_config = json.loads(config.provider_config)

        # Use injected dependencies or create them (for backward compatibility)
        if encryption_service is None:
            from services.cloud_providers import EncryptionService

            encryption_service = EncryptionService()
        if storage_factory is None:
            from services.cloud_providers import StorageFactory

            storage_factory = StorageFactory(rclone)

        # Get sensitive field names without creating storage (since config is encrypted)
        if config.provider == "s3":
            sensitive_fields = ["access_key", "secret_key"]
        elif config.provider == "sftp":
            sensitive_fields = ["password", "private_key"]
        else:
            sensitive_fields = []

        # Decrypt sensitive fields first
        decrypted_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

        # Now create storage with decrypted config for testing
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

        # Parse JSON configuration
        import json

        provider_config = json.loads(config.provider_config)

        # First, create a temporary storage instance to get sensitive field names
        # We need to do this without full validation since the config is encrypted
        if config.provider == "s3":
            sensitive_fields = ["access_key", "secret_key"]
        elif config.provider == "sftp":
            sensitive_fields = ["password", "private_key"]
        else:
            sensitive_fields = []

        # Decrypt sensitive fields
        decrypted_provider_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

        # Build decrypted config for template
        decrypted_config = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "path_prefix": config.path_prefix,
            "enabled": config.enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

        # Add all provider-specific fields from decrypted JSON
        decrypted_config.update(decrypted_provider_config)

        return decrypted_config
