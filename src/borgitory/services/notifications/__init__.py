"""
Notification system for Borgitory.

This package provides a pluggable notification system with support for
multiple notification providers (Pushover, Discord, Slack, Email, etc.).
"""

from .registry import (
    register_provider,
    get_supported_providers,
    get_all_provider_info,
    is_provider_registered,
    NotificationProviderRegistry,
)
from .registry_factory import NotificationRegistryFactory
from .types import (
    NotificationMessage,
    NotificationResult,
    NotificationType,
    NotificationPriority,
    ConnectionInfo,
)

# Import providers to ensure they are registered
from .providers import pushover_provider, discord_provider

__all__ = [
    "register_provider",
    "get_supported_providers",
    "get_all_provider_info",
    "is_provider_registered",
    "NotificationProviderRegistry",
    "NotificationRegistryFactory",
    "NotificationMessage",
    "NotificationResult",
    "NotificationType",
    "NotificationPriority",
    "ConnectionInfo",
    "pushover_provider",
    "discord_provider",
]
