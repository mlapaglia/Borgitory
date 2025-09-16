"""
Amazon S3 cloud storage implementation.

This module provides S3-specific storage operations with clean separation
from business logic and easy testability.
"""

from typing import Callable, Optional
from pydantic import Field, field_validator

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo


class S3StorageConfig(CloudStorageConfig):
    """Configuration for Amazon S3 storage"""

    bucket_name: str = Field(..., min_length=3, max_length=63)
    access_key: str = Field(..., min_length=1)
    secret_key: str = Field(..., min_length=1)
    region: str = Field(default="us-east-1")
    endpoint_url: Optional[str] = None
    storage_class: str = Field(default="STANDARD")

    @field_validator("bucket_name")
    @classmethod
    def validate_bucket_name(cls, v: str) -> str:
        """Normalize bucket name to lowercase"""
        return v.lower()

    @field_validator("storage_class")
    @classmethod
    def validate_storage_class(cls, v: str) -> str:
        """Validate and normalize storage class"""
        valid_classes = {
            "STANDARD",
            "REDUCED_REDUNDANCY",
            "STANDARD_IA",
            "ONEZONE_IA",
            "INTELLIGENT_TIERING",
            "GLACIER",
            "DEEP_ARCHIVE",
        }
        v_upper = v.upper()
        if v_upper not in valid_classes:
            raise ValueError(
                f"Invalid storage class. Must be one of: {', '.join(valid_classes)}"
            )
        return v_upper


class S3Storage(CloudStorage):
    """
    Amazon S3 cloud storage implementation.

    This class handles S3-specific operations while maintaining the clean
    CloudStorage interface for easy testing and integration.
    """

    def __init__(self, config: S3StorageConfig, rclone_service):
        """
        Initialize S3 storage.

        Args:
            config: Validated S3 configuration
            rclone_service: Injected rclone service for I/O operations
        """
        self._config = config
        self._rclone_service = rclone_service

    async def upload_repository(
        self,
        repository_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[SyncEvent], None]] = None,
    ) -> None:
        """Upload repository to S3"""
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting S3 upload to bucket {self._config.bucket_name}",
                )
            )

        try:
            # Use rclone service for actual I/O - this is what we'll mock in tests
            async for progress in self._rclone_service.sync_repository_to_s3(
                repository_path=repository_path,
                access_key_id=self._config.access_key,
                secret_access_key=self._config.secret_key,
                bucket_name=self._config.bucket_name,
                path_prefix=remote_path,
                region=self._config.region,
                endpoint_url=self._config.endpoint_url,
                storage_class=self._config.storage_class,
            ):
                if progress_callback and progress.get("type") == "progress":
                    progress_callback(
                        SyncEvent(
                            type=SyncEventType.PROGRESS,
                            message=progress.get("message", "Uploading..."),
                            progress=progress.get("percentage", 0.0),
                        )
                    )

            if progress_callback:
                progress_callback(
                    SyncEvent(
                        type=SyncEventType.COMPLETED,
                        message="S3 upload completed successfully",
                    )
                )

        except Exception as e:
            error_msg = f"S3 upload failed: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        """Test S3 connection"""
        try:
            result = await self._rclone_service.test_s3_connection(
                access_key_id=self._config.access_key,
                secret_access_key=self._config.secret_key,
                bucket_name=self._config.bucket_name,
                region=self._config.region,
                endpoint_url=self._config.endpoint_url,
            )
            return result.get("status") == "success"
        except Exception:
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get S3 connection info for display"""
        return ConnectionInfo(
            provider="s3",
            details={
                "bucket": self._config.bucket_name,
                "region": self._config.region,
                "endpoint": self._config.endpoint_url or "default",
                "storage_class": self._config.storage_class,
                "access_key": f"{self._config.access_key[:4]}***{self._config.access_key[-4:]}"
                if len(self._config.access_key) > 8
                else "***",
            },
        )

    def get_sensitive_fields(self) -> list[str]:
        """S3 sensitive fields"""
        return ["access_key", "secret_key"]
