"""
Cloud Storage Implementations

This package contains storage implementations for different cloud providers.
Each provider is in its own file for better organization and maintainability.

Importing this module will automatically register all providers with the registry.
"""

from .base import CloudStorage, CloudStorageConfig
from .s3_storage import (
    S3Storage,
    S3StorageConfig,
    S3Provider,
)  # Import provider to trigger registration
from .sftp_storage import (
    SFTPStorage,
    SFTPStorageConfig,
    SFTPProvider,
)  # Import provider to trigger registration
from .smb_storage import (
    SMBStorage,
    SMBStorageConfig,
    SMBProvider,
)  # Import provider to trigger registration

# Import registry functions for convenience
from ..registry import get_supported_providers, get_all_provider_info

__all__ = [
    "CloudStorage",
    "CloudStorageConfig",
    "S3Storage",
    "S3StorageConfig",
    "S3Provider",
    "SFTPStorage",
    "SFTPStorageConfig",
    "SFTPProvider",
    "SMBStorage",
    "SMBStorageConfig",
    "SMBProvider",
    # Registry functions
    "get_supported_providers",
    "get_all_provider_info",
]
