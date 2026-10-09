"""
Notification system for Borgitory.

Notifications are delivered through Apprise (https://github.com/caronc/apprise),
which supports a large number of services through a single URL-based interface.
"""

from .apprise_catalog import AppriseCatalog, AppriseService, get_apprise_catalog
from .types import NotificationMessage, NotificationResult, NotificationType

__all__ = [
    "AppriseCatalog",
    "AppriseService",
    "get_apprise_catalog",
    "NotificationMessage",
    "NotificationResult",
    "NotificationType",
]
