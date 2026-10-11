"""
Type definitions for notification system.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

import apprise


class NotificationType(str, Enum):
    """Types of notifications that can be sent"""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def to_apprise_notify_type(self) -> apprise.NotifyType:
        """Map to the closest Apprise notification type"""
        mapping = {
            NotificationType.SUCCESS: apprise.NotifyType.SUCCESS,
            NotificationType.FAILURE: apprise.NotifyType.FAILURE,
            NotificationType.ERROR: apprise.NotifyType.FAILURE,
            NotificationType.WARNING: apprise.NotifyType.WARNING,
            NotificationType.INFO: apprise.NotifyType.INFO,
        }
        return mapping[self]


@dataclass
class NotificationMessage:
    """Message to be sent via Apprise"""

    title: str
    message: str
    notification_type: NotificationType = NotificationType.INFO


@dataclass
class NotificationResult:
    """Result of a notification send attempt"""

    success: bool
    message: str
    error: Optional[str] = None
    details: List[str] = field(default_factory=list)
