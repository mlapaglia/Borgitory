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
        """Create a new cloud sync configuration."""

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

        db_config = CloudSyncConfig(
            name=config.name,
            provider=config.provider,
            path_prefix=config.path_prefix or "",
        )

        if config.provider == "s3":
            db_config.bucket_name = config.bucket_name

            if not config.access_key or not config.secret_key:
                raise HTTPException(
                    status_code=400,
                    detail="S3 configurations require access_key and secret_key",
                )

            db_config.set_credentials(config.access_key, config.secret_key)

        elif config.provider == "sftp":
            db_config.host = config.host
            db_config.port = config.port or 22
            db_config.username = config.username
            db_config.remote_path = config.remote_path

            if not config.host or not config.username or not config.remote_path:
                raise HTTPException(
                    status_code=400,
                    detail="SFTP configurations require host, username, and remote_path",
                )

            if not config.password and not config.private_key:
                raise HTTPException(
                    status_code=400,
                    detail="SFTP configurations require either password or private_key",
                )

            db_config.set_sftp_credentials(config.password, config.private_key)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {config.provider}. Supported providers: s3, sftp",
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

        if config.provider == "s3":
            access_key, secret_key = config.get_credentials()

            result = await rclone.test_s3_connection(
                access_key_id=access_key,
                secret_access_key=secret_key,
                bucket_name=config.bucket_name,
            )

        elif config.provider == "sftp":
            password, private_key = config.get_sftp_credentials()

            result = await rclone.test_sftp_connection(
                host=config.host,
                username=config.username,
                remote_path=config.remote_path,
                port=config.port or 22,
                password=password if password else None,
                private_key=private_key if private_key else None,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider for testing: {config.provider}",
            )

        return result
