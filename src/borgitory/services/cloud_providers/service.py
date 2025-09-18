"""
Cloud sync service layer.

This module provides the high-level service interface for cloud sync operations,
including configuration validation, storage creation, and encryption handling.
"""

import json
import logging
from typing import Dict, Any, Callable, Optional

from borgitory.services.rclone_service import RcloneService

from .types import CloudSyncConfig, SyncResult
from .storage import CloudStorage
from .registry import get_config_class, get_storage_class, get_supported_providers
from .orchestration import CloudSyncer, LoggingSyncEventHandler

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates cloud storage configurations"""

    def validate_config(self, provider: str, config: Dict[str, Any]) -> Any:
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
        config_class = get_config_class(provider)
        if config_class is None:
            supported = get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        return config_class(**config)


class StorageFactory:
    """Factory for creating cloud storage instances"""

    def __init__(self, rclone_service: RcloneService) -> None:
        """
        Initialize storage factory.

        Args:
            rclone_service: Rclone service for I/O operations
        """
        self._rclone_service = rclone_service
        self._validator = ConfigValidator()

    def create_storage(self, provider: str, config: Dict[str, Any]) -> CloudStorage:
        """
        Create a cloud storage instance.

        Args:
            provider: Provider name (e.g., s3, sftp, smb)
            config: Configuration dictionary

        Returns:
            CloudStorage instance

        Raises:
            ValueError: If provider is unknown or config is invalid
        """
        validated_config = self._validator.validate_config(provider, config)

        storage_class = get_storage_class(provider)
        if storage_class is None:
            supported = get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        storage_instance = storage_class(validated_config, self._rclone_service)
        return storage_instance

    def get_supported_providers(self) -> list[str]:
        """Get list of supported provider names."""
        return get_supported_providers()


class EncryptionService:
    """Handles encryption/decryption of sensitive configuration fields"""

    def encrypt_sensitive_fields(
        self, config: Dict[str, Any], sensitive_fields: list[str]
    ) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary
            sensitive_fields: List of field names to encrypt

        Returns:
            Configuration with sensitive fields encrypted
        """
        from borgitory.models.database import get_cipher_suite

        encrypted_config = config.copy()
        cipher = get_cipher_suite()

        for field in sensitive_fields:
            if field in encrypted_config and encrypted_config[field]:
                encrypted_value = cipher.encrypt(
                    str(encrypted_config[field]).encode()
                ).decode()
                encrypted_config[f"encrypted_{field}"] = encrypted_value
                del encrypted_config[field]

        return encrypted_config

    def decrypt_sensitive_fields(
        self, config: Dict[str, Any], sensitive_fields: list[str]
    ) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary with encrypted fields
            sensitive_fields: List of field names to decrypt

        Returns:
            Configuration with sensitive fields decrypted
        """
        from borgitory.models.database import get_cipher_suite

        decrypted_config = config.copy()
        cipher = get_cipher_suite()

        for field in sensitive_fields:
            encrypted_field = f"encrypted_{field}"
            if (
                encrypted_field in decrypted_config
                and decrypted_config[encrypted_field]
            ):
                decrypted_value = cipher.decrypt(
                    decrypted_config[encrypted_field].encode()
                ).decode()
                decrypted_config[field] = decrypted_value
                del decrypted_config[encrypted_field]

        return decrypted_config


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

    def prepare_config_for_storage(self, provider: str, config: Dict[str, Any]) -> str:
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

    def load_config_from_storage(
        self, provider: str, stored_config: str
    ) -> Dict[str, Any]:
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
