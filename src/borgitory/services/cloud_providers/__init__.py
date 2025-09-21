"""
Cloud Providers Package

This package provides a clean, testable architecture for cloud storage operations.
It separates concerns into focused components that are easy to test and maintain.

Architecture Components:
- types: Core types (SyncResult, SyncEvent, etc.)
- storage/: Storage interface and provider implementations
- orchestration: Business logic coordination
- service: High-level service interface
- config_service: Configuration loading and management
"""

from .types import SyncResult, SyncEvent, SyncEventType, CloudSyncConfig, ConnectionInfo
from .storage import (
    CloudStorage,
    S3Storage,
    SFTPStorage,
    S3StorageConfig,
    SFTPStorageConfig,
)
from .orchestration import CloudSyncer, SyncEventHandler, LoggingSyncEventHandler
from .service import (
    CloudSyncService,
    StorageFactory,
    ConfigValidator,
)
from borgitory.services.encryption_service import EncryptionService
from .config_service import (
    ConfigLoadService,
    DatabaseConfigLoadService,
    MockConfigLoadService,
)

__all__ = [
    "SyncResult",
    "SyncEvent",
    "SyncEventType",
    "CloudSyncConfig",
    "ConnectionInfo",
    "CloudStorage",
    "S3Storage",
    "SFTPStorage",
    "S3StorageConfig",
    "SFTPStorageConfig",
    "CloudSyncer",
    "SyncEventHandler",
    "LoggingSyncEventHandler",
    "CloudSyncService",
    "StorageFactory",
    "ConfigValidator",
    "EncryptionService",
    "ConfigLoadService",
    "DatabaseConfigLoadService",
    "MockConfigLoadService",
]
