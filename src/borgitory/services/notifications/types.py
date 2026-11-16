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

    @property
    def severity(self) -> int:
        """Severity rank: 0 = success/info, 1 = warning, 2 = failure/error"""
        if self in (NotificationType.ERROR, NotificationType.FAILURE):
            return 2
        if self == NotificationType.WARNING:
            return 1
        return 0


class NotificationPolicy(str, Enum):
    """Which job outcomes a notification configuration sends"""

    ALL = "all"
    WARNINGS_AND_FAILURES = "warnings_and_failures"
    FAILURES_ONLY = "failures_only"

    @property
    def label(self) -> str:
        labels = {
            NotificationPolicy.ALL: "All events",
            NotificationPolicy.WARNINGS_AND_FAILURES: "Warnings & failures",
            NotificationPolicy.FAILURES_ONLY: "Failures only",
        }
        return labels[self]

    @property
    def min_severity(self) -> int:
        thresholds = {
            NotificationPolicy.ALL: 0,
            NotificationPolicy.WARNINGS_AND_FAILURES: 1,
            NotificationPolicy.FAILURES_ONLY: 2,
        }
        return thresholds[self]

    def allows(self, notification_type: NotificationType) -> bool:
        """Whether a notification of this type should be sent under this policy"""
        return notification_type.severity >= self.min_severity

    @classmethod
    def from_value(cls, value: Optional[str]) -> "NotificationPolicy":
        """Parse a stored value, falling back to ALL for missing or unknown values"""
        try:
            return cls(value) if value else cls.ALL
        except ValueError:
            return cls.ALL


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
