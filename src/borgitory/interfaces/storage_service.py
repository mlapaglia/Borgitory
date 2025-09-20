"""
Storage service protocol interface.

Defines the contract for cloud storage and data persistence services.
"""

from typing import Protocol, Optional, Callable
from borgitory.services.cloud_providers.types import CloudSyncConfig, SyncResult


class StorageService(Protocol):
    """Protocol for cloud storage services"""

    async def execute_sync(
        self,
        config: CloudSyncConfig,
        repository_path: str,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> SyncResult:
        """
        Execute a cloud sync operation.
        Args:
            config: Cloud sync configuration
            repository_path: Path to the repository to sync
            output_callback: Optional callback for real-time output
        Returns:
            SyncResult indicating success/failure and details
        """
        ...

    async def test_connection(self, config: CloudSyncConfig) -> bool:
        """
        Test connection to cloud storage.

        Args:
            config: Cloud sync configuration

        Returns:
            True if connection successful, False otherwise
        """
        ...
