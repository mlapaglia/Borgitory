"""
Protocol interfaces for notification services.
"""

from typing import Protocol, Dict, List, Optional, TYPE_CHECKING, Union

from borgitory.services.notifications.types import NotificationMessage

if TYPE_CHECKING:
    from borgitory.services.notifications.types import (
        NotificationConfig,
        NotificationResult,
    )


class NotificationServiceProtocol(Protocol):
    """Protocol for the new provider-based notification service."""

    async def send_notification(
        self,
        config: "NotificationConfig",
        message: NotificationMessage,
    ) -> "NotificationResult":
        """Send a notification using the provider system."""
        ...

    async def test_connection(
        self,
        config: "NotificationConfig",
    ) -> bool:
        """Test connection to notification service."""
        ...

    def get_connection_info(
        self,
        config: "NotificationConfig",
    ) -> str:
        """Get connection information for display."""
        ...

    def prepare_config_for_storage(
        self,
        provider: str,
        config: Dict[str, Union[str, int, float, bool]],
    ) -> str:
        """Prepare configuration for database storage."""
        ...

    def load_config_from_storage(
        self,
        provider: str,
        stored_config: str,
    ) -> Dict[str, Union[str, int, float, bool]]:
        """Load configuration from database storage."""
        ...


class NotificationConfigServiceProtocol(Protocol):
    """Protocol for notification configuration management."""

    def create_config(
        self,
        provider: str,
        config_data: Dict[str, Union[str, int, float, bool]],
    ) -> "NotificationConfig":
        """Create a new notification configuration."""
        ...

    def get_config(
        self,
        config_id: int,
    ) -> Optional["NotificationConfig"]:
        """Get a notification configuration by ID."""
        ...

    def list_configs(self) -> List["NotificationConfig"]:
        """List all notification configurations."""
        ...

    def update_config(
        self,
        config_id: int,
        config_data: Dict[str, Union[str, int, float, bool]],
    ) -> Optional["NotificationConfig"]:
        """Update a notification configuration."""
        ...

    def delete_config(
        self,
        config_id: int,
    ) -> bool:
        """Delete a notification configuration."""
        ...
