"""
Protocol interfaces for notification services.
"""

from typing import Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.services.notifications.apprise_storage import (
        AppriseSubmission,
        StoredAppriseConfig,
    )
    from borgitory.services.notifications.types import (
        NotificationMessage,
        NotificationResult,
    )


class NotificationServiceProtocol(Protocol):
    """Protocol for the Apprise-backed notification service."""

    async def send_notification(
        self,
        config: "StoredAppriseConfig",
        message: "NotificationMessage",
    ) -> "NotificationResult":
        """Send a notification to every URL in the configuration."""
        ...

    async def send_test(
        self,
        config: "StoredAppriseConfig",
    ) -> "NotificationResult":
        """Send a test notification."""
        ...

    def build_config(
        self,
        submission: "AppriseSubmission",
        existing: Optional["StoredAppriseConfig"] = None,
    ) -> "StoredAppriseConfig":
        """Validate a form submission and build the configuration to store."""
        ...

    def prepare_config_for_storage(
        self,
        config: "StoredAppriseConfig",
    ) -> str:
        """Serialize configuration for database storage."""
        ...

    def load_config_from_storage(
        self,
        provider: str,
        stored: str,
    ) -> "StoredAppriseConfig":
        """Load configuration from database storage."""
        ...
