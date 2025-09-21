"""
Base notification provider interface and configuration.

This module defines the abstract interface that all notification providers
must implement, ensuring consistency across different providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List
from pydantic import BaseModel, ConfigDict

from ..types import NotificationMessage, NotificationResult, ConnectionInfo


class NotificationProviderConfig(BaseModel):
    """
    Base configuration for all notification provider implementations.

    Each provider should extend this with provider-specific fields.
    """

    model_config = ConfigDict(extra="forbid")  # Prevent unknown fields


class NotificationProvider(ABC):
    """
    Abstract interface for notification providers.

    This interface is designed to be:
    - Easy to implement for new providers
    - Simple to mock and test
    - Focused on single responsibility
    """

    def __init__(self, config: NotificationProviderConfig) -> None:
        """Initialize the provider with configuration."""
        self.config = config

    @abstractmethod
    async def send_notification(
        self, message: NotificationMessage
    ) -> NotificationResult:
        """
        Send a notification message.

        Args:
            message: The notification message to send

        Returns:
            NotificationResult indicating success/failure and details
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connection to the notification service.

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
    def get_sensitive_fields(self) -> List[str]:
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
