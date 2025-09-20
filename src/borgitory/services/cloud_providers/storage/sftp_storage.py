"""
SFTP cloud storage implementation.

This module provides SFTP-specific storage operations with clean separation
from business logic and easy testability.
"""

import re
from typing import Callable, Dict, Optional
from pydantic import Field, field_validator, model_validator

from borgitory.services.rclone_service import RcloneService
from borgitory.models.database import Repository

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider, RcloneMethodMapping


class SFTPStorageConfig(CloudStorageConfig):
    """Configuration for SFTP storage"""

    host: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    password: Optional[str] = None
    private_key: Optional[str] = None
    remote_path: str = Field(..., min_length=1)
    host_key_checking: bool = Field(default=True)

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate SFTP host format"""
        import re

        if not re.match(r"^[a-zA-Z0-9.-]+$", v):
            raise ValueError(
                "Host must contain only letters, numbers, periods, and hyphens"
            )
        if v.startswith(".") or v.endswith("."):
            raise ValueError("Host cannot start or end with a period")
        if ".." in v:
            raise ValueError("Host cannot contain consecutive periods")
        return v.lower()

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate SFTP username format"""
        import re

        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                "Username must contain only letters, numbers, periods, underscores, and hyphens"
            )
        return v

    @field_validator("remote_path")
    @classmethod
    def validate_remote_path(cls, v: str) -> str:
        """Validate and normalize remote path"""
        if not v:
            raise ValueError("Remote path cannot be empty")

        if not v.startswith("/"):
            v = "/" + v

        # Remove trailing slash unless it's root
        if len(v) > 1:
            v = v.rstrip("/")

        if not re.match(r"^/[a-zA-Z0-9._/-]*$", v):
            raise ValueError("Remote path contains invalid characters")

        return v

    @model_validator(mode="after")
    def validate_auth_method(self) -> "SFTPStorageConfig":
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

    def __init__(
        self, config: SFTPStorageConfig, rclone_service: RcloneService
    ) -> None:
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
            # Create a simple repository object with the path

            repository_obj = Repository()
            repository_obj.path = repository_path

            async for progress in self._rclone_service.sync_repository_to_sftp(
                repository=repository_obj,
                host=self._config.host,
                username=self._config.username,
                remote_path=self._config.remote_path,
                port=self._config.port,
                password=self._config.password,
                private_key=self._config.private_key,
                path_prefix=remote_path,
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

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """Get SFTP-specific display details for the UI"""
        host = config_dict.get("host", "Unknown")
        port = config_dict.get("port", 22)
        username = config_dict.get("username", "Unknown")
        remote_path = config_dict.get("remote_path", "Unknown")
        auth_method = "password" if config_dict.get("password") else "private_key"

        provider_details = f"""
            <div><strong>Host:</strong> {host}:{port}</div>
            <div><strong>Username:</strong> {username}</div>
            <div><strong>Remote Path:</strong> {remote_path}</div>
            <div><strong>Auth Method:</strong> {auth_method}</div>
        """.strip()

        return {"provider_name": "SFTP (SSH)", "provider_details": provider_details}

    @classmethod
    def get_rclone_mapping(cls) -> RcloneMethodMapping:
        """Define rclone parameter mapping for SFTP"""
        return RcloneMethodMapping(
            sync_method="sync_repository_to_sftp",
            test_method="test_sftp_connection",
            parameter_mapping={
                "repository": "repository",
                "host": "host",
                "username": "username",
                "remote_path": "remote_path",
                "port": "port",
                "password": "password",
                "private_key": "private_key",
            },
            required_params=["repository", "host", "username"],
            optional_params={
                "port": 22,
                "path_prefix": "",
            },
        )


@register_provider(
    name="sftp",
    label="SFTP (SSH)",
    description="Secure File Transfer Protocol",
    supports_encryption=True,
    supports_versioning=False,
    requires_credentials=True,
    rclone_mapping=RcloneMethodMapping(
        sync_method="sync_repository_to_sftp",
        test_method="test_sftp_connection",
        parameter_mapping={
            "repository": "repository",
            "host": "host",
            "username": "username",
            "remote_path": "remote_path",
            "port": "port",
            "password": "password",
            "private_key": "private_key",
        },
        required_params=["repository", "host", "username"],
        optional_params={
            "port": 22,
            "path_prefix": "",
        },
    ),
)
class SFTPProvider:
    """SFTP provider registration"""

    config_class = SFTPStorageConfig
    storage_class = SFTPStorage
