"""
Configuration service for loading cloud sync configurations.

This service handles the database access and legacy configuration conversion,
keeping the JobExecutor clean and testable.
"""

import json
import logging
from typing import Optional, Callable, Any, Dict
from abc import ABC, abstractmethod

from .types import CloudSyncConfig

logger = logging.getLogger(__name__)


class ConfigLoadService(ABC):
    """Abstract service for loading cloud sync configurations"""

    @abstractmethod
    async def load_config(self, config_id: int) -> Optional[CloudSyncConfig]:
        """
        Load a cloud sync configuration by ID.

        Args:
            config_id: Configuration ID to load

        Returns:
            CloudSyncConfig if found and enabled, None otherwise
        """
        pass


class DatabaseConfigLoadService(ConfigLoadService):
    """Service that loads configurations from database"""

    def __init__(self, db_session_factory: Callable[[], Any]) -> None:
        """
        Initialize with database session factory.

        Args:
            db_session_factory: Factory function for creating database sessions
        """
        self._db_session_factory = db_session_factory

    async def load_config(self, config_id: int) -> Optional[CloudSyncConfig]:
        """Load configuration from database"""
        try:
            from borgitory.models.database import CloudSyncConfig as DbCloudSyncConfig

            with self._db_session_factory() as db:
                db_config = (
                    db.query(DbCloudSyncConfig)
                    .filter(DbCloudSyncConfig.id == config_id)
                    .first()
                )

                if not db_config or not db_config.enabled:
                    logger.info(f"Cloud sync config {config_id} not found or disabled")
                    return None

                # Convert database config to service config
                provider_config = {}
                if db_config.provider_config:
                    # New JSON-based configuration
                    provider_config = json.loads(db_config.provider_config)
                else:
                    # Handle legacy configuration
                    provider_config = self._convert_legacy_config(db_config)

                return CloudSyncConfig(
                    provider=db_config.provider,
                    config=provider_config,
                    path_prefix=db_config.path_prefix or "",
                    name=db_config.name,
                )

        except Exception as e:
            logger.error(f"Failed to load config {config_id}: {str(e)}")
            return None

    def _convert_legacy_config(self, db_config: Any) -> Dict[str, Any]:
        """Convert legacy database configuration to new format"""
        if db_config.provider == "s3":
            access_key, secret_key = db_config.get_credentials()
            return {
                "bucket_name": db_config.bucket_name,
                "access_key": access_key,
                "secret_key": secret_key,
                "region": "us-east-1",
                "storage_class": "STANDARD",
            }
        elif db_config.provider == "sftp":
            password, private_key = db_config.get_sftp_credentials()
            config = {
                "host": db_config.host,
                "username": db_config.username,
                "remote_path": db_config.remote_path,
                "port": db_config.port or 22,
                "host_key_checking": True,
            }
            if password:
                config["password"] = password
            if private_key:
                config["private_key"] = private_key
            return config
        else:
            raise ValueError(f"Unknown legacy provider: {db_config.provider}")


class MockConfigLoadService(ConfigLoadService):
    """Mock service for testing - returns predefined configurations"""

    def __init__(self, configs: dict[int, CloudSyncConfig]) -> None:
        """
        Initialize with predefined configurations.

        Args:
            configs: Dictionary mapping config IDs to CloudSyncConfig objects
        """
        self._configs = configs

    async def load_config(self, config_id: int) -> Optional[CloudSyncConfig]:
        """Return predefined config or None"""
        return self._configs.get(config_id)
