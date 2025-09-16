"""
SMB cloud storage implementation.

This module provides SMB/CIFS-specific storage operations with clean separation
from business logic and easy testability.
"""

from typing import Callable, Optional
from pydantic import Field, field_validator, model_validator

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider


class SMBStorageConfig(CloudStorageConfig):
    """Configuration for SMB storage"""

    host: str = Field(
        ..., min_length=1, description="SMB server hostname to connect to"
    )
    user: str = Field(default="guest", description="SMB username")
    port: int = Field(default=445, ge=1, le=65535, description="SMB port number")
    pass_: Optional[str] = Field(default=None, alias="pass", description="SMB password")
    domain: str = Field(
        default="WORKGROUP", description="Domain name for NTLM authentication"
    )
    spn: Optional[str] = Field(default=None, description="Service principal name")
    use_kerberos: bool = Field(default=False, description="Use Kerberos authentication")
    idle_timeout: str = Field(
        default="1m0s", description="Max time before closing idle connections"
    )
    hide_special_share: bool = Field(
        default=True, description="Hide special shares (e.g. print$)"
    )
    case_insensitive: bool = Field(
        default=True, description="Whether the server is case-insensitive"
    )
    kerberos_ccache: Optional[str] = Field(
        default=None, description="Path to the Kerberos credential cache"
    )
    share_name: str = Field(
        ..., min_length=1, description="SMB share name to connect to"
    )

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Validate SMB host format"""
        import re

        # Basic validation for hostname or IP
        if not re.match(r"^[a-zA-Z0-9.-]+$", v):
            raise ValueError(
                "Host must contain only letters, numbers, periods, and hyphens"
            )
        if v.startswith(".") or v.endswith("."):
            raise ValueError("Host cannot start or end with a period")
        if ".." in v:
            raise ValueError("Host cannot contain consecutive periods")
        return v.lower()

    @field_validator("user")
    @classmethod
    def validate_user(cls, v: str) -> str:
        """Validate SMB username format"""
        import re

        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                "Username must contain only letters, numbers, periods, underscores, and hyphens"
            )
        return v

    @field_validator("share_name")
    @classmethod
    def validate_share_name(cls, v: str) -> str:
        """Validate SMB share name format"""
        import re

        # SMB share names can contain letters, numbers, spaces, and some special characters
        if not re.match(r"^[a-zA-Z0-9 ._-]+$", v):
            raise ValueError(
                "Share name can only contain letters, numbers, spaces, periods, underscores, and hyphens"
            )
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain name format"""
        import re

        if not re.match(r"^[a-zA-Z0-9.-]+$", v):
            raise ValueError(
                "Domain must contain only letters, numbers, periods, and hyphens"
            )
        return v.upper()

    @field_validator("idle_timeout")
    @classmethod
    def validate_idle_timeout(cls, v: str) -> str:
        """Validate idle timeout format"""
        import re

        # Validate duration format like "1m0s", "30s", "2h", etc.
        if not re.match(r"^\d+[smh](\d+[smh])*$", v):
            raise ValueError(
                "Idle timeout must be in duration format (e.g., '1m0s', '30s', '2h')"
            )
        return v

    @model_validator(mode="after")
    def validate_auth_combination(self):
        """Validate authentication method combinations"""
        if self.use_kerberos and self.pass_:
            raise ValueError("Cannot use both Kerberos and password authentication")

        if self.use_kerberos and not self.kerberos_ccache:
            # Kerberos without explicit ccache is allowed (uses default locations)
            pass

        return self


class SMBStorage(CloudStorage):
    """
    SMB cloud storage implementation.

    This class handles SMB/CIFS-specific operations while maintaining the clean
    CloudStorage interface for easy testing and integration.
    """

    def __init__(self, config: SMBStorageConfig, rclone_service):
        """
        Initialize SMB storage.

        Args:
            config: Validated SMB configuration
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
        """Upload repository to SMB share"""
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting SMB upload to {self._config.host}:{self._config.share_name}",
                )
            )

        try:
            # Use rclone service for actual I/O
            async for progress in self._rclone_service.sync_repository_to_smb(
                repository_path=repository_path,
                host=self._config.host,
                user=self._config.user,
                password=self._config.pass_,
                port=self._config.port,
                domain=self._config.domain,
                share_name=self._config.share_name,
                path_prefix=remote_path,
                spn=self._config.spn,
                use_kerberos=self._config.use_kerberos,
                idle_timeout=self._config.idle_timeout,
                hide_special_share=self._config.hide_special_share,
                case_insensitive=self._config.case_insensitive,
                kerberos_ccache=self._config.kerberos_ccache,
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
                        message="SMB upload completed successfully",
                    )
                )

        except Exception as e:
            error_msg = f"SMB upload failed: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        """Test SMB connection"""
        try:
            result = await self._rclone_service.test_smb_connection(
                host=self._config.host,
                user=self._config.user,
                password=self._config.pass_,
                port=self._config.port,
                domain=self._config.domain,
                share_name=self._config.share_name,
                spn=self._config.spn,
                use_kerberos=self._config.use_kerberos,
                idle_timeout=self._config.idle_timeout,
                hide_special_share=self._config.hide_special_share,
                case_insensitive=self._config.case_insensitive,
                kerberos_ccache=self._config.kerberos_ccache,
            )
            return result.get("status") == "success"
        except Exception:
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get SMB connection info for display"""
        auth_method = "kerberos" if self._config.use_kerberos else "password"
        return ConnectionInfo(
            provider="smb",
            details={
                "host": self._config.host,
                "port": self._config.port,
                "user": self._config.user,
                "domain": self._config.domain,
                "share_name": self._config.share_name,
                "auth_method": auth_method,
                "case_insensitive": self._config.case_insensitive,
                "password": f"{self._config.pass_[:2]}***{self._config.pass_[-2:]}"
                if self._config.pass_ and len(self._config.pass_) > 4
                else "***"
                if self._config.pass_
                else None,
            },
        )

    def get_sensitive_fields(self) -> list[str]:
        """SMB sensitive fields that should be encrypted"""
        return ["pass"]

    def get_display_details(self, config_dict: dict) -> dict:
        """Get SMB-specific display details for the UI"""
        host = config_dict.get("host", "Unknown")
        port = config_dict.get("port", 445)
        user = config_dict.get("user", "Unknown")
        domain = config_dict.get("domain", "WORKGROUP")
        share_name = config_dict.get("share_name", "Unknown")
        auth_method = "kerberos" if config_dict.get("use_kerberos") else "password"

        provider_details = f"""
            <div><strong>Host:</strong> {host}:{port}</div>
            <div><strong>Share:</strong> {share_name}</div>
            <div><strong>User:</strong> {domain}\\{user}</div>
            <div><strong>Auth Method:</strong> {auth_method}</div>
        """.strip()

        return {"provider_name": "SMB/CIFS", "provider_details": provider_details}


@register_provider(
    name="smb",
    label="SMB/CIFS",
    description="Server Message Block / Common Internet File System",
    supports_encryption=True,
    supports_versioning=False,
    requires_credentials=True,
)
class SMBProvider:
    """SMB provider registration"""

    config_class = SMBStorageConfig
    storage_class = SMBStorage
