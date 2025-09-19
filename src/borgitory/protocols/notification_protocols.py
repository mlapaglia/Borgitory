"""
Protocol interfaces for notification services.
"""

from typing import Protocol, Dict, List, Any, Optional


class NotificationServiceProtocol(Protocol):
    """Protocol for notification services (PushoverService, etc.)."""

    async def send_notification(
        self,
        user_key: str,
        app_token: str,
        title: str,
        message: str,
        priority: int = 0,
        sound: str = "default",
    ) -> bool:
        """Send a notification."""
        ...

    async def send_notification_with_response(
        self,
        user_key: str,
        app_token: str,
        title: str,
        message: str,
        priority: int = 0,
        sound: str = "default",
    ) -> tuple[bool, str]:
        """Send a notification and return detailed response."""
        ...

    async def test_pushover_connection(
        self,
        user_key: str,
        app_token: str,
    ) -> Dict[str, Any]:
        """Test connection to notification service."""
        ...

    async def send_backup_success_notification(
        self,
        user_key: str,
        app_token: str,
        repository_name: str,
        job_type: str,
        duration: Optional[str] = None,
        archive_count: Optional[int] = None,
    ) -> bool:
        """Send a backup success notification."""
        ...


class NotificationConfigServiceProtocol(Protocol):
    """Protocol for notification configuration management."""

    def create_config(
        self,
        provider: str,
        config_data: Dict[str, Any],
    ) -> Any:  # NotificationConfig model
        """Create a new notification configuration."""
        ...

    def get_config(
        self,
        config_id: int,
    ) -> Optional[Any]:  # NotificationConfig model
        """Get a notification configuration by ID."""
        ...

    def list_configs(self) -> List[Any]:  # List[NotificationConfig]
        """List all notification configurations."""
        ...

    def update_config(
        self,
        config_id: int,
        config_data: Dict[str, Any],
    ) -> Optional[Any]:  # NotificationConfig model
        """Update a notification configuration."""
        ...

    def delete_config(
        self,
        config_id: int,
    ) -> bool:
        """Delete a notification configuration."""
        ...
