"""
Protocol interfaces for Borgitory services.

This module defines structural interfaces that services must implement,
enabling loose coupling and better testability.
"""

# Command execution protocols
from .command_protocols import (
    CommandResult,
    CommandRunnerProtocol,
    ProcessExecutorProtocol,
)

# Storage and volume protocols
from .storage_protocols import (
    VolumeServiceProtocol,
)

# Job management protocols
from .job_protocols import (
    JobStatusProtocol,
    JobManagerProtocol,
)

# Repository and backup protocols
from .repository_protocols import (
    RepositoryInfo,
    ArchiveInfo,
    BackupServiceProtocol,
    ArchiveServiceProtocol,
    RepositoryServiceProtocol,
)

# Notification protocols
from .notification_protocols import (
    NotificationServiceProtocol,
    NotificationConfigServiceProtocol,
)

# Cloud service protocols
from .cloud_protocols import (
    CloudStorageProtocol,
    CloudSyncServiceProtocol,
    CloudSyncConfigServiceProtocol,
    EncryptionServiceProtocol,
    StorageFactoryProtocol,
)

__all__ = [
    # Command protocols
    "CommandResult",
    "CommandRunnerProtocol",
    "ProcessExecutorProtocol",
    # Storage protocols
    "VolumeServiceProtocol",
    # Job protocols
    "JobStatusProtocol",
    "JobManagerProtocol",
    # Repository protocols
    "RepositoryInfo",
    "ArchiveInfo",
    "BackupServiceProtocol",
    "ArchiveServiceProtocol",
    "RepositoryServiceProtocol",
    # Notification protocols
    "NotificationServiceProtocol",
    "NotificationConfigServiceProtocol",
    # Cloud protocols
    "CloudStorageProtocol",
    "CloudSyncServiceProtocol",
    "CloudSyncConfigServiceProtocol",
    "EncryptionServiceProtocol",
    "StorageFactoryProtocol",
]
