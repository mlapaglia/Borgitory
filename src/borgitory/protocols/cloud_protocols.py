"""
Protocol interfaces for cloud storage and synchronization services.
"""

from typing import Protocol, Dict, List, Optional, Callable, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.models.database import CloudSyncConfig


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
    ) -> List[Dict[str, Union[str, int, float, bool, None]]]:
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

    def get_connection_info(self) -> Dict[str, Union[str, int, float, bool, None]]:
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
    ) -> Dict[str, Union[str, int, float, bool, None]]:  # SyncResult
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
        config: Dict[str, Union[str, int, float, bool, None]],
    ) -> str:
        """Prepare configuration for database storage by encrypting sensitive fields."""
        ...

    def load_config_from_storage(
        self,
        provider: str,
        stored_config: str,
    ) -> Dict[str, Union[str, int, float, bool, None]]:
        """Load configuration from database storage by decrypting sensitive fields."""
        ...


class EncryptionServiceProtocol(Protocol):
    """Protocol for encryption/decryption services."""

    def encrypt_sensitive_fields(
        self,
        config: Dict[str, Union[str, int, float, bool, None]],
        sensitive_fields: List[str],
    ) -> Dict[str, Union[str, int, float, bool, None]]:
        """Encrypt sensitive fields in configuration."""
        ...

    def decrypt_sensitive_fields(
        self,
        config: Dict[str, Union[str, int, float, bool, None]],
        sensitive_fields: List[str],
    ) -> Dict[str, Union[str, int, float, bool, None]]:
        """Decrypt sensitive fields in configuration."""
        ...


class StorageFactoryProtocol(Protocol):
    """Protocol for cloud storage factory."""

    def create_storage(
        self,
        provider: str,
        config: Dict[str, Union[str, int, float, bool, None]],
    ) -> CloudStorageProtocol:
        """Create a cloud storage instance."""
        ...

    def get_supported_providers(self) -> List[str]:
        """Get list of supported provider names."""
        ...
