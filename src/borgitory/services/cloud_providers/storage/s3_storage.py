"""
Amazon S3 cloud storage implementation.

This module provides S3-specific storage operations with clean separation
from business logic and easy testability.
"""

import re
from typing import Callable, Dict, Optional
from pydantic import Field, field_validator

from borgitory.services.rclone_service import RcloneService

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider, RcloneMethodMapping


class S3StorageConfig(CloudStorageConfig):
    """Configuration for Amazon S3 storage"""

    bucket_name: str = Field(..., min_length=3, max_length=63)
    access_key: str = Field(..., min_length=16, max_length=128)
    secret_key: str = Field(..., min_length=40, max_length=128)
    region: str = Field(default="us-east-1")
    endpoint_url: Optional[str] = None
    storage_class: str = Field(default="STANDARD")

    @field_validator("access_key")
    @classmethod
    def validate_access_key(cls, v: str) -> str:
        """Validate AWS Access Key ID format"""
        if not v.startswith("AKIA"):
            raise ValueError("AWS Access Key ID must start with 'AKIA'")
        if len(v) != 20:
            raise ValueError("AWS Access Key ID must be exactly 20 characters long")
        if not v.isalnum():
            raise ValueError(
                "AWS Access Key ID must contain only alphanumeric characters"
            )
        return v.upper()

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate AWS Secret Access Key format"""
        if len(v) != 40:
            raise ValueError("AWS Secret Access Key must be exactly 40 characters long")

        if not re.match(r"^[A-Za-z0-9+/=]+$", v):
            raise ValueError("AWS Secret Access Key contains invalid characters")
        return v

    @field_validator("bucket_name")
    @classmethod
    def validate_bucket_name(cls, v: str) -> str:
        """Validate and normalize S3 bucket name"""
        v_lower = v.lower()

        if not (3 <= len(v_lower) <= 63):
            raise ValueError("Bucket name must be between 3 and 63 characters long")

        if not re.match(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", v_lower):
            raise ValueError(
                "Bucket name must start and end with a letter or number, and contain only lowercase letters, numbers, periods, and hyphens"
            )

        if ".." in v_lower:
            raise ValueError("Bucket name cannot contain consecutive periods")

        if ".-" in v_lower or "-." in v_lower:
            raise ValueError("Bucket name cannot contain periods adjacent to hyphens")

        return v_lower

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

    def __init__(self, config: S3StorageConfig, rclone_service: RcloneService) -> None:
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
            # Create a simple repository object with the path
            from borgitory.models.database import Repository

            repository_obj = Repository()
            repository_obj.path = repository_path

            async for progress in self._rclone_service.sync_repository_to_s3(
                repository=repository_obj,
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
                            message=str(progress.get("message", "Uploading...")),
                            progress=float(progress.get("percentage", 0.0) or 0.0),
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

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """Get S3-specific display details for the UI"""
        bucket_name = config_dict.get("bucket_name", "Unknown")
        region = config_dict.get("region", "us-east-1")
        storage_class = config_dict.get("storage_class", "STANDARD")

        provider_details = f"""
            <div><strong>Bucket:</strong> {bucket_name}</div>
            <div><strong>Region:</strong> {region}</div>
            <div><strong>Storage Class:</strong> {storage_class}</div>
        """.strip()

        return {"provider_name": "AWS S3", "provider_details": provider_details}

    @classmethod
    def get_rclone_mapping(cls) -> RcloneMethodMapping:
        """Define rclone parameter mapping for S3"""
        return RcloneMethodMapping(
            sync_method="sync_repository_to_s3",
            test_method="test_s3_connection",
            parameter_mapping={
                "access_key": "access_key_id",
                "secret_key": "secret_access_key",
                "bucket_name": "bucket_name",
                "region": "region",
                "endpoint_url": "endpoint_url",
                "storage_class": "storage_class",
            },
            required_params=[
                "repository",
                "access_key_id",
                "secret_access_key",
                "bucket_name",
            ],
            optional_params={"path_prefix": "", "region": "us-east-1"},
        )


@register_provider(
    name="s3",
    label="AWS S3",
    description="Amazon S3 compatible storage",
    supports_encryption=True,
    supports_versioning=True,
    requires_credentials=True,
    rclone_mapping=RcloneMethodMapping(
        sync_method="sync_repository_to_s3",
        test_method="test_s3_connection",
        parameter_mapping={
            "access_key": "access_key_id",
            "secret_key": "secret_access_key",
            "bucket_name": "bucket_name",
            "region": "region",
            "endpoint_url": "endpoint_url",
            "storage_class": "storage_class",
        },
        required_params=[
            "repository",
            "access_key_id",
            "secret_access_key",
            "bucket_name",
        ],
        optional_params={"path_prefix": "", "region": "us-east-1"},
    ),
)
class S3Provider:
    """S3 provider registration"""

    config_class = S3StorageConfig
    storage_class = S3Storage
