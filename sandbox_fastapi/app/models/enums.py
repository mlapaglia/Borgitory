"""
Enums for all constrained string values following FastAPI best practices.

Following the guide: "Use enums for constrained string values"
This eliminates magic strings and provides type safety.
"""

from enum import Enum


class JobStatus(str, Enum):
    """Job execution status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enum."""
    BACKUP = "backup"
    PRUNE = "prune"
    CHECK = "check"
    NOTIFICATION = "notification"
    IMPORT = "import"


class TaskStatus(str, Enum):
    """Individual task status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskType(str, Enum):
    """Task type enum."""
    BACKUP = "backup"
    PRUNE = "prune"
    CHECK = "check"
    NOTIFICATION = "notification"
    CLOUD_SYNC = "cloud_sync"


class NotificationProvider(str, Enum):
    """Notification provider enum."""
    PUSHOVER = "pushover"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"


class CompressionType(str, Enum):
    """Borg compression algorithm enum."""
    NONE = "none"
    LZ4 = "lz4"
    ZLIB = "zlib"
    LZMA = "lzma"
    ZSTD = "zstd"


class NotificationPriority(int, Enum):
    """Pushover notification priority levels."""
    LOWEST = -2
    LOW = -1
    NORMAL = 0
    HIGH = 1
    EMERGENCY = 2


class JobPriority(int, Enum):
    """Job execution priority."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4