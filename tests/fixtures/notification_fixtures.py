"""
Helpers for creating Apprise notification configurations in tests.
"""

from typing import Dict, Optional

from borgitory.models.database import NotificationConfig
from borgitory.services.notifications.apprise_catalog import get_apprise_catalog
from borgitory.services.notifications.apprise_storage import (
    APPRISE_PROVIDER,
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.service import NotificationService

DISCORD_WEBHOOK_ID = "redacted-webhook-id"
DISCORD_WEBHOOK_TOKEN = "super-secret-webhook-token"


def discord_values(botname: str = "Borgitory") -> Dict[str, str]:
    return {
        "webhook_id": DISCORD_WEBHOOK_ID,
        "webhook_token": DISCORD_WEBHOOK_TOKEN,
        "botname": botname,
    }


def build_stored_config(
    submission: Optional[AppriseSubmission] = None,
) -> StoredAppriseConfig:
    service = NotificationService(catalog=get_apprise_catalog())
    return service.build_config(
        submission
        or AppriseSubmission(mode="service", service="discord", values=discord_values())
    )


def create_notification_config(
    name: str,
    enabled: bool = True,
    submission: Optional[AppriseSubmission] = None,
    stored: Optional[StoredAppriseConfig] = None,
) -> NotificationConfig:
    """Create a NotificationConfig row in the Apprise format (Discord by default)."""
    config = NotificationConfig()
    config.name = name
    config.provider = APPRISE_PROVIDER
    config.enabled = enabled
    config.provider_config = (stored or build_stored_config(submission)).encode()
    return config


def discord_form(name: str, **overrides: str) -> Dict[str, str]:
    """Form data as posted by the add/edit form for a Discord notification."""
    form = {"name": name, "service": "discord"}
    for key, value in discord_values().items():
        form[f"fields[{key}]"] = value
    form.update(overrides)
    return form
