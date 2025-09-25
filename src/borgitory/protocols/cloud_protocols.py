"""
Protocol interfaces for cloud storage and synchronization services.
"""

from typing import Protocol, List, Optional, Callable, TYPE_CHECKING
from borgitory.custom_types import ConfigDict

if TYPE_CHECKING:
    from borgitory.models.database import CloudSyncConfig
    from borgitory.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate
    from borgitory.services.cloud_providers import StorageFactory
    from borgitory.services.encryption_service import EncryptionService


class CloudStorageProtocol(Protocol):
    """Protocol for cloud storage operations."""

    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
    ) -> bool:
        """Upload a file to cloud storage."""
        ...

    async def download_file(
        self,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Download a file from cloud storage."""
        ...

    async def list_files(
        self,
        remote_path: str = "",
    ) -> List[ConfigDict]:
        """List files in cloud storage."""
        ...

    async def delete_file(
        self,
        remote_path: str,
    ) -> bool:
        """Delete a file from cloud storage."""
        ...

    async def test_connection(self) -> bool:
        """Test connection to cloud storage."""
        ...

    def get_connection_info(self) -> ConfigDict:
        """Get connection information for display."""
        ...

    def get_sensitive_fields(self) -> List[str]:
        """Get list of sensitive configuration fields."""
        ...


class CloudSyncServiceProtocol(Protocol):
    """Protocol for cloud synchronization operations."""

    async def execute_sync(
        self,
        config: "CloudSyncConfig",  # CloudSyncConfig
        repository_path: str,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> ConfigDict:  # SyncResult
        """Execute a cloud sync operation."""
        ...

    async def test_connection(
        self,
        config: "CloudSyncConfig",  # CloudSyncConfig
    ) -> bool:
        """Test connection to cloud storage."""
        ...

    def get_connection_info(
        self,
        config: "CloudSyncConfig",  # CloudSyncConfig
    ) -> str:
        """Get connection information for display."""
        ...

    def prepare_config_for_storage(
        self,
        provider: str,
        config: ConfigDict,
    ) -> str:
        """Prepare configuration for database storage by encrypting sensitive fields."""
        ...

    def load_config_from_storage(
        self,
        provider: str,
        stored_config: str,
    ) -> ConfigDict:
        """Load configuration from database storage by decrypting sensitive fields."""
        ...


class CloudSyncConfigServiceProtocol(Protocol):
    """Protocol for cloud sync configuration management (CRUD operations)."""

    def create_cloud_sync_config(
        self, config: "CloudSyncConfigCreate"
    ) -> "CloudSyncConfig":
        """Create a new cloud sync configuration."""
        ...

    def get_cloud_sync_configs(self) -> List["CloudSyncConfig"]:
        """Get all cloud sync configurations."""
        ...

    def get_cloud_sync_config_by_id(self, config_id: int) -> "CloudSyncConfig":
        """Get a cloud sync configuration by ID."""
        ...

    def update_cloud_sync_config(
        self, config_id: int, config_update: "CloudSyncConfigUpdate"
    ) -> "CloudSyncConfig":
        """Update a cloud sync configuration."""
        ...

    def delete_cloud_sync_config(self, config_id: int) -> None:
        """Delete a cloud sync configuration."""
        ...

    def enable_cloud_sync_config(self, config_id: int) -> "CloudSyncConfig":
        """Enable a cloud sync configuration."""
        ...

    def disable_cloud_sync_config(self, config_id: int) -> "CloudSyncConfig":
        """Disable a cloud sync configuration."""
        ...

    def get_decrypted_config_for_editing(
        self,
        config_id: int,
        encryption_service: "EncryptionService",
        storage_factory: "StorageFactory",
    ) -> ConfigDict:
        """Get decrypted configuration for editing."""
        ...


class EncryptionServiceProtocol(Protocol):
    """Protocol for encryption/decryption services."""

    def encrypt_sensitive_fields(
        self,
        config: ConfigDict,
        sensitive_fields: List[str],
    ) -> ConfigDict:
        """Encrypt sensitive fields in configuration."""
        ...

    def decrypt_sensitive_fields(
        self,
        config: ConfigDict,
        sensitive_fields: List[str],
    ) -> ConfigDict:
        """Decrypt sensitive fields in configuration."""
        ...


class StorageFactoryProtocol(Protocol):
    """Protocol for cloud storage factory."""

    def create_storage(
        self,
        provider: str,
        config: ConfigDict,
    ) -> CloudStorageProtocol:
        """Create a cloud storage instance."""
        ...

    def get_supported_providers(self) -> List[str]:
        """Get list of supported provider names."""
        ...
