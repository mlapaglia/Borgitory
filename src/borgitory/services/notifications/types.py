"""
Type definitions for notification system.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
from borgitory.custom_types import ConfigDict


class NotificationType(str, Enum):
    """Types of notifications that can be sent"""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class NotificationPriority(int, Enum):
    """Notification priority levels"""

    LOWEST = -2
    LOW = -1
    NORMAL = 0
    HIGH = 1
    EMERGENCY = 2


@dataclass
class NotificationMessage:
    """Message to be sent via notification provider"""

    title: str
    message: str
    notification_type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.NORMAL
    metadata: Optional[Dict[str, object]] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class NotificationResult:
    """Result of a notification send attempt"""

    success: bool
    provider: str
    message: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, object]] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConnectionInfo:
    """Connection information for display purposes"""

    provider: str
    endpoint: str
    status: str = "unknown"
    additional_info: Optional[Dict[str, object]] = None

    def __post_init__(self) -> None:
        if self.additional_info is None:
            self.additional_info = {}

    def __str__(self) -> str:
        """String representation for display"""
        return f"{self.provider.title()} API - {self.endpoint} ({self.status})"


@dataclass
class NotificationConfig:
    """Configuration for a notification provider"""

    provider: str
    config: ConfigDict
    name: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"{self.provider.title()} Notification"
