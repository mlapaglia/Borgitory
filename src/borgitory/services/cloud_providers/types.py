"""
Core types for the cloud provider system.

These types provide the foundation for a clean, testable architecture
with proper separation of concerns.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from borgitory.custom_types import ConfigDict


class SyncEventType(Enum):
    """Types of sync events that can occur during cloud operations"""

    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    ERROR = "error"
    LOG = "log"


@dataclass
class SyncEvent:
    """
    Immutable event representing something that happened during sync.

    Simple, easy to test, and clear in purpose.
    """

    type: SyncEventType
    message: str
    progress: float = 0.0
    error: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = now_utc()


@dataclass
class SyncResult:
    """
    Simple result of a sync operation.

    Much easier to test than async generators - just check the fields.
    """

    success: bool
    bytes_transferred: int = 0
    files_transferred: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0

    @classmethod
    def success_result(
        cls,
        bytes_transferred: int = 0,
        files_transferred: int = 0,
        duration_seconds: float = 0.0,
    ) -> "SyncResult":
        """Create a successful sync result"""
        return cls(
            success=True,
            bytes_transferred=bytes_transferred,
            files_transferred=files_transferred,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def error_result(cls, error: str) -> "SyncResult":
        """Create an error sync result"""
        return cls(success=False, error=error)


@dataclass
class CloudSyncConfig:
    """
    Clean configuration for cloud sync operations.

    Separates configuration from business logic.
    """

    provider: str
    config: ConfigDict
    path_prefix: str = ""
    name: str = ""

    def get_config_value(self, key: str, default: object = None) -> object:
        """Get a configuration value with optional default"""
        return self.config.get(key, default)


@dataclass
class ConnectionInfo:
    """
    Sanitized connection information for display/logging.

    Contains no sensitive data.
    """

    provider: str
    details: Dict[str, object]

    def __str__(self) -> str:
        detail_parts = [f"{k}={v}" for k, v in self.details.items()]
        return f"{self.provider}({', '.join(detail_parts)})"
