"""
Cloud Providers Package

This package contains the cloud storage provider implementations for Borgitory.
Each provider implements the CloudProvider interface and handles syncing repositories
to their respective cloud storage services.
"""

from .base import CloudProvider, ProviderConfig
from .factory import CloudProviderFactory

# Import providers to register them with the factory
from .s3_provider import S3Provider
from .sftp_provider import SFTPProvider

__all__ = ["CloudProvider", "ProviderConfig", "CloudProviderFactory", "S3Provider", "SFTPProvider"]
