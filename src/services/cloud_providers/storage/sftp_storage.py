"""
SFTP cloud storage implementation.

This module provides SFTP-specific storage operations with clean separation
from business logic and easy testability.
"""

from typing import Callable, Optional
from pydantic import Field, field_validator, model_validator

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo


class SFTPStorageConfig(CloudStorageConfig):
    """Configuration for SFTP storage"""

    host: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    password: Optional[str] = None
    private_key: Optional[str] = None
    remote_path: str = Field(..., min_length=1)
    host_key_checking: bool = Field(default=True)

    @field_validator("remote_path")
    @classmethod
    def normalize_remote_path(cls, v: str) -> str:
        """Ensure remote path starts with / and doesn't end with /"""
        if not v.startswith("/"):
            v = "/" + v
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_auth_method(self):
        """Ensure at least one authentication method is provided"""
        if not self.password and not self.private_key:
            raise ValueError("Either password or private_key must be provided")
        return self


class SFTPStorage(CloudStorage):
    """
    SFTP cloud storage implementation.

    This class handles SFTP-specific operations while maintaining the clean
    CloudStorage interface for easy testing and integration.
    """

    def __init__(self, config: SFTPStorageConfig, rclone_service):
        """
        Initialize SFTP storage.

        Args:
            config: Validated SFTP configuration
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
        """Upload repository to SFTP server"""
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting SFTP upload to {self._config.host}:{self._config.remote_path}",
                )
            )

        try:
            # Use rclone service for actual I/O
            async for progress in self._rclone_service.sync_repository_to_sftp(
                repository_path=repository_path,
                host=self._config.host,
                username=self._config.username,
                remote_path=self._config.remote_path,
                port=self._config.port,
                password=self._config.password,
                private_key=self._config.private_key,
                path_prefix=remote_path,
                host_key_checking=self._config.host_key_checking,
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
                        message="SFTP upload completed successfully",
                    )
                )

        except Exception as e:
            error_msg = f"SFTP upload failed: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        """Test SFTP connection"""
        try:
            result = await self._rclone_service.test_sftp_connection(
                host=self._config.host,
                username=self._config.username,
                remote_path=self._config.remote_path,
                port=self._config.port,
                password=self._config.password,
                private_key=self._config.private_key,
                host_key_checking=self._config.host_key_checking,
            )
            return result.get("status") == "success"
        except Exception:
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get SFTP connection info for display"""
        auth_method = "password" if self._config.password else "private_key"
        return ConnectionInfo(
            provider="sftp",
            details={
                "host": self._config.host,
                "port": self._config.port,
                "username": self._config.username,
                "remote_path": self._config.remote_path,
                "auth_method": auth_method,
                "host_key_checking": self._config.host_key_checking,
            },
        )

    def get_sensitive_fields(self) -> list[str]:
        """SFTP sensitive fields"""
        return ["password", "private_key"]
