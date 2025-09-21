"""
Base cloud storage interface and configuration.

This module defines the abstract interface that all cloud storage providers
must implement, ensuring consistency across different providers.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict

from ..types import SyncEvent, ConnectionInfo


class CloudStorageConfig(BaseModel):
    """
    Base configuration for all cloud storage implementations.

    Each provider should extend this with provider-specific fields.
    """

    model_config = ConfigDict(extra="forbid")  # Prevent unknown fields


class CloudStorage(ABC):
    """
    Abstract interface for cloud storage operations.

    This interface is designed to be:
    - Easy to implement for new providers
    - Simple to mock and test
    - Free of async generator complexity
    - Focused on single responsibility
    """

    @abstractmethod
    async def upload_repository(
        self,
        repository_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[SyncEvent], None]] = None,
    ) -> None:
        """
        Upload a repository to cloud storage.

        Args:
            repository_path: Local path to the repository
            remote_path: Remote path where repository should be stored
            progress_callback: Optional callback for progress events

        Raises:
            Exception: If upload fails
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connection to the cloud storage.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def get_connection_info(self) -> ConnectionInfo:
        """
        Get sanitized connection information for logging/display.

        Returns:
            ConnectionInfo with non-sensitive details
        """
        pass

    @abstractmethod
    def get_sensitive_fields(self) -> list[str]:
        """
        Get list of field names that contain sensitive data.

        Returns:
            List of sensitive field names for encryption
        """
        pass

    @abstractmethod
    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """
        Get provider-specific display details for the UI.

        Args:
            config_dict: Provider configuration as dictionary

        Returns:
            Dictionary with 'provider_name' and 'provider_details' (HTML string)
        """
        pass
