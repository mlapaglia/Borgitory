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

        # Set legacy fields for backward compatibility (if migration hasn't run yet)
        if config.provider.value == "s3" and hasattr(db_config, "bucket_name"):
            db_config.bucket_name = config.provider_config.get("bucket_name")
            if (
                "access_key" in config.provider_config
                and "secret_key" in config.provider_config
            ):
                db_config.set_credentials(
                    config.provider_config["access_key"],
                    config.provider_config["secret_key"],
                )
        elif config.provider.value == "sftp" and hasattr(db_config, "host"):
            db_config.host = config.provider_config.get("host")
            db_config.port = config.provider_config.get("port", 22)
            db_config.username = config.provider_config.get("username")
            db_config.remote_path = config.provider_config.get("remote_path")
            if (
                "password" in config.provider_config
                or "private_key" in config.provider_config
            ):
                db_config.set_sftp_credentials(
                    config.provider_config.get("password"),
                    config.provider_config.get("private_key"),
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

        for field, value in config_update.model_dump(exclude_unset=True).items():
            if field in ["access_key", "secret_key", "password", "private_key"]:
                continue
            setattr(config, field, value)

        if config.provider == "s3":
            if config_update.access_key and config_update.secret_key:
                config.set_credentials(
                    config_update.access_key, config_update.secret_key
                )
        elif config.provider == "sftp":
            if config_update.password or config_update.private_key:
                config.set_sftp_credentials(
                    config_update.password, config_update.private_key
                )

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
        self, config_id: int, rclone: RcloneService
    ) -> dict:
        """Test a cloud sync configuration."""
        config = self.get_cloud_sync_config_by_id(config_id)

        # Parse JSON configuration
        import json
        from services.cloud_providers import EncryptionService, StorageFactory

        provider_config = json.loads(config.provider_config)

        # Decrypt sensitive fields
        encryption_service = EncryptionService()
        storage_factory = StorageFactory(rclone)
        storage = storage_factory.create_storage(config.provider, provider_config)
        sensitive_fields = storage.get_sensitive_fields()
        decrypted_config = encryption_service.decrypt_sensitive_fields(
            provider_config, sensitive_fields
        )

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
