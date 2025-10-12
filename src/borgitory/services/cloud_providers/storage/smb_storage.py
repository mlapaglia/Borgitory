"""
SMB cloud storage implementation.

This module provides SMB/CIFS-specific storage operations with clean separation
from business logic and easy testability.
"""

import asyncio
import os
import re
import subprocess
import tempfile
import time
from typing import Callable, Dict, Optional, List, AsyncGenerator, Union, cast
from pydantic import Field, field_validator, model_validator

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.rclone_types import ConnectionTestResult, ProgressData

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider, RcloneMethodMapping


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

        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                "Username must contain only letters, numbers, periods, underscores, and hyphens"
            )
        return v

    @field_validator("share_name")
    @classmethod
    def validate_share_name(cls, v: str) -> str:
        """Validate SMB share name format"""

        if not re.match(r"^[a-zA-Z0-9 ._-]+$", v):
            raise ValueError(
                "Share name can only contain letters, numbers, spaces, periods, underscores, and hyphens"
            )
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain name format"""

        if not re.match(r"^[a-zA-Z0-9.-]+$", v):
            raise ValueError(
                "Domain must contain only letters, numbers, periods, and hyphens"
            )
        return v.upper()

    @field_validator("idle_timeout")
    @classmethod
    def validate_idle_timeout(cls, v: str) -> str:
        """Validate idle timeout format"""

        if not re.match(r"^\d+[smh](\d+[smh])*$", v):
            raise ValueError(
                "Idle timeout must be in duration format (e.g., '1m0s', '30s', '2h')"
            )
        return v

    @model_validator(mode="after")
    def validate_auth_combination(self) -> "SMBStorageConfig":
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

    def __init__(
        self,
        config: SMBStorageConfig,
        command_executor: CommandExecutorProtocol,
        file_service: FileServiceProtocol,
    ) -> None:
        """
        Initialize SMB storage.

        Args:
            config: Validated SMB configuration
            command_executor: Command executor for running external commands
            file_service: File service for file operations
        """
        self._config = config
        self._command_executor = command_executor
        self._file_service = file_service

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
            async for progress in self.sync_repository_to_smb(
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
                if not progress_callback:
                    continue

                progress_type = progress.get("type")
                if progress_type == "progress":
                    progress_callback(
                        SyncEvent(
                            type=SyncEventType.PROGRESS,
                            message=str(progress.get("message", "Uploading...")),
                            progress=float(progress.get("percentage", 0.0) or 0.0),
                        )
                    )
                elif progress_type == "log":
                    progress_callback(
                        SyncEvent(
                            type=SyncEventType.LOG,
                            message=str(progress.get("message", "")),
                        )
                    )
                elif progress_type == "error":
                    error_msg = str(progress.get("message", "Unknown error"))
                    progress_callback(
                        SyncEvent(
                            type=SyncEventType.ERROR,
                            message=error_msg,
                            error=error_msg,
                        )
                    )
                    raise Exception(error_msg)
                elif progress_type == "completed":
                    if progress.get("status") != "success":
                        error_msg = f"SMB sync failed with return code {progress.get('return_code')}"
                        progress_callback(
                            SyncEvent(
                                type=SyncEventType.ERROR,
                                message=error_msg,
                                error=error_msg,
                            )
                        )
                        raise Exception(error_msg)

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
            result = await self.test_smb_connection(
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

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
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

    @classmethod
    def get_rclone_mapping(cls) -> RcloneMethodMapping:
        """Define rclone parameter mapping for SMB"""
        return RcloneMethodMapping(
            sync_method="sync_repository_to_smb",
            test_method="test_smb_connection",
            parameter_mapping={
                "repository": "repository_path",
                "host": "host",
                "user": "user",
                "pass": "password",
                "port": "port",
                "domain": "domain",
                "share_name": "share_name",
                "spn": "spn",
                "use_kerberos": "use_kerberos",
                "idle_timeout": "idle_timeout",
                "hide_special_share": "hide_special_share",
                "case_insensitive": "case_insensitive",
                "kerberos_ccache": "kerberos_ccache",
            },
            required_params=["repository", "host", "user", "share_name"],
            optional_params={"port": 445, "domain": "WORKGROUP", "path_prefix": ""},
        )

    def _obscure_password(self, password: str) -> str:
        """Obscure password using rclone's method"""
        try:
            result = subprocess.run(
                ["rclone", "obscure", password],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return password

        except Exception:
            return password

    def _build_smb_flags(
        self,
        host: str,
        user: str,
        password: Optional[str] = None,
        port: int = 445,
        domain: str = "WORKGROUP",
        spn: Optional[str] = None,
        use_kerberos: bool = False,
        idle_timeout: str = "1m0s",
        hide_special_share: bool = True,
        case_insensitive: bool = True,
        kerberos_ccache: Optional[str] = None,
    ) -> List[str]:
        """Build SMB configuration flags for rclone command"""
        flags = [
            "--smb-host",
            host,
            "--smb-user",
            user,
            "--smb-port",
            str(port),
            "--smb-domain",
            domain,
            "--smb-idle-timeout",
            idle_timeout,
        ]

        if password:
            obscured_password = self._obscure_password(password)
            flags.extend(["--smb-pass", obscured_password])

        if spn:
            flags.extend(["--smb-spn", spn])

        if use_kerberos:
            flags.append("--smb-use-kerberos")

        if kerberos_ccache:
            flags.extend(["--smb-kerberos-ccache", kerberos_ccache])

        if hide_special_share:
            flags.append("--smb-hide-special-share")

        if case_insensitive:
            flags.append("--smb-case-insensitive")

        return flags

    async def sync_repository_to_smb(
        self,
        repository_path: str,
        host: str,
        user: str,
        share_name: str,
        password: Optional[str] = None,
        port: int = 445,
        domain: str = "WORKGROUP",
        path_prefix: str = "",
        spn: Optional[str] = None,
        use_kerberos: bool = False,
        idle_timeout: str = "1m0s",
        hide_special_share: bool = True,
        case_insensitive: bool = True,
        kerberos_ccache: Optional[str] = None,
        progress_callback: Optional[Callable[[ProgressData], None]] = None,
    ) -> AsyncGenerator[ProgressData, None]:
        """Sync a Borg repository to SMB using Rclone with SMB backend"""

        smb_path = f":smb:{share_name}"
        if path_prefix:
            smb_path = f"{smb_path}/{path_prefix}"

        command = [
            "rclone",
            "sync",
            repository_path,
            smb_path,
            "--progress",
            "--stats",
            "1s",
            "--verbose",
        ]

        smb_flags = self._build_smb_flags(
            host,
            user,
            password,
            port,
            domain,
            spn,
            use_kerberos,
            idle_timeout,
            hide_special_share,
            case_insensitive,
            kerberos_ccache,
        )
        command.extend(smb_flags)

        try:
            process = await self._command_executor.create_subprocess(
                command=command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            yield cast(
                ProgressData,
                {
                    "type": "started",
                    "command": " ".join(
                        [c for c in command if not c.startswith("--smb-pass")]
                    ),
                    "pid": process.pid,
                },
            )

            async def read_stream(
                stream: Optional[asyncio.StreamReader], stream_type: str
            ) -> AsyncGenerator[ProgressData, None]:
                if stream is None:
                    return
                while True:
                    line = await stream.readline()
                    if not line:
                        break

                    decoded_line = line.decode("utf-8").strip()
                    progress_data = self.parse_rclone_progress(decoded_line)

                    if progress_data:
                        yield cast(ProgressData, {"type": "progress", **progress_data})
                    else:
                        yield cast(
                            ProgressData,
                            {
                                "type": "log",
                                "stream": stream_type,
                                "message": decoded_line,
                            },
                        )

            async for item in self._merge_async_generators(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
            ):
                yield item

            return_code = await process.wait()

            yield cast(
                ProgressData,
                {
                    "type": "completed",
                    "return_code": return_code,
                    "status": "success" if return_code == 0 else "failed",
                },
            )

        except Exception as e:
            yield cast(ProgressData, {"type": "error", "message": str(e)})

    async def test_smb_connection(
        self,
        host: str,
        user: str,
        share_name: str,
        password: Optional[str] = None,
        port: int = 445,
        domain: str = "WORKGROUP",
        spn: Optional[str] = None,
        use_kerberos: bool = False,
        idle_timeout: str = "1m0s",
        hide_special_share: bool = True,
        case_insensitive: bool = True,
        kerberos_ccache: Optional[str] = None,
    ) -> ConnectionTestResult:
        """Test SMB connection by listing share contents"""
        try:
            import logging

            logger = logging.getLogger(__name__)

            smb_path = f":smb:{share_name}"

            command = ["rclone", "lsd", smb_path, "--max-depth", "1", "--verbose"]

            smb_flags = self._build_smb_flags(
                host,
                user,
                password,
                port,
                domain,
                spn,
                use_kerberos,
                idle_timeout,
                hide_special_share,
                case_insensitive,
                kerberos_ccache,
            )
            command.extend(smb_flags)

            result = await self._command_executor.execute_command(
                command=command, timeout=30.0
            )

            logger.info(f"SMB test command return code: {result.return_code}")
            if result.stderr.strip():
                logger.info(f"SMB test stderr: {result.stderr.strip()}")
            if result.stdout.strip():
                logger.info(f"SMB test stdout: {result.stdout.strip()}")

            if result.success:
                test_result = await self._test_smb_write_permissions(
                    host,
                    user,
                    share_name,
                    password,
                    port,
                    domain,
                    spn,
                    use_kerberos,
                    idle_timeout,
                    hide_special_share,
                    case_insensitive,
                    kerberos_ccache,
                )

                if test_result.get("status") == "success":
                    return {
                        "status": "success",
                        "message": f"Successfully connected to SMB share {share_name} on {host}",
                        "details": {
                            "can_list": True,
                            "can_write": bool(test_result.get("can_write", False)),
                            "stdout": result.stdout,
                        },
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"Connected to SMB share but write test failed: {test_result.get('message', 'Unknown error')}",
                        "details": {
                            "can_list": True,
                            "can_write": False,
                            "stdout": result.stdout,
                            "write_error": test_result.get("message"),
                        },
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to connect to SMB share {share_name} on {host}",
                    "details": {
                        "return_code": result.return_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                }

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"SMB connection test failed: {e}")
            return {
                "status": "error",
                "message": f"Connection test failed: {str(e)}",
                "details": {"exception": str(e)},
            }

    async def _test_smb_write_permissions(
        self,
        host: str,
        user: str,
        share_name: str,
        password: Optional[str] = None,
        port: int = 445,
        domain: str = "WORKGROUP",
        spn: Optional[str] = None,
        use_kerberos: bool = False,
        idle_timeout: str = "1m0s",
        hide_special_share: bool = True,
        case_insensitive: bool = True,
        kerberos_ccache: Optional[str] = None,
    ) -> ConnectionTestResult:
        """Test write permissions on SMB share"""

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".borgitory_test"
            ) as f:
                f.write(f"Borgitory SMB test file - {time.time()}")
                temp_file = f.name

            test_filename = f"borgitory_test_{int(time.time())}.txt"
            remote_test_path = f":smb:{share_name}/{test_filename}"

            command = ["rclone", "copy", temp_file, remote_test_path, "--verbose"]

            smb_flags = self._build_smb_flags(
                host,
                user,
                password,
                port,
                domain,
                spn,
                use_kerberos,
                idle_timeout,
                hide_special_share,
                case_insensitive,
                kerberos_ccache,
            )
            command.extend(smb_flags)

            upload_result = await self._command_executor.execute_command(
                command=command, timeout=30.0
            )

            if upload_result.success:
                delete_command = [
                    "rclone",
                    "deletefile",
                    f"{remote_test_path}/{test_filename}",
                    "--verbose",
                ]
                delete_command.extend(smb_flags)

                await self._command_executor.execute_command(
                    command=delete_command, timeout=30.0
                )

                return {
                    "status": "success",
                    "can_write": True,
                    "message": "Write permissions confirmed",
                }
            else:
                return {
                    "status": "error",
                    "can_write": False,
                    "message": f"Write test failed: {upload_result.stderr}",
                }

        except Exception as e:
            return {
                "status": "error",
                "can_write": False,
                "message": f"Write permission test failed: {str(e)}",
            }
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    def parse_rclone_progress(
        self, line: str
    ) -> Optional[Dict[str, Union[str, int, float]]]:
        """Parse Rclone progress output"""
        if "Transferred:" in line:
            try:
                parts = line.split()
                if len(parts) >= 6:
                    transferred = parts[1]
                    total = parts[4].rstrip(",")
                    percentage = parts[5].rstrip("%,")
                    speed = parts[6] if len(parts) > 6 else "0"

                    return {
                        "transferred": transferred,
                        "total": total,
                        "percentage": float(percentage)
                        if percentage.replace(".", "").isdigit()
                        else 0,
                        "speed": speed,
                    }
            except (IndexError, ValueError):
                pass

        if "ETA" in line:
            try:
                eta_part = line.split("ETA")[-1].strip()
                return {"eta": eta_part}
            except (ValueError, KeyError):
                pass

        return None

    async def _merge_async_generators(
        self, *async_generators: AsyncGenerator[ProgressData, None]
    ) -> AsyncGenerator[ProgressData, None]:
        """Merge multiple async generators into one"""
        tasks = []
        for gen in async_generators:

            async def wrapper(
                g: AsyncGenerator[ProgressData, None],
            ) -> AsyncGenerator[ProgressData, None]:
                async for item in g:
                    yield item

            tasks.append(wrapper(gen))

        for task in tasks:
            async for item in task:
                yield item


@register_provider(
    name="smb",
    label="SMB/CIFS",
    description="Server Message Block / Common Internet File System",
    supports_encryption=True,
    supports_versioning=False,
    requires_credentials=True,
    rclone_mapping=RcloneMethodMapping(
        sync_method="sync_repository_to_smb",
        test_method="test_smb_connection",
        parameter_mapping={
            "repository": "repository_path",
            "host": "host",
            "user": "user",
            "pass": "password",  # SMB config uses pass (alias for pass_), rclone expects password
            "port": "port",
            "domain": "domain",
            "share_name": "share_name",
            "spn": "spn",
            "use_kerberos": "use_kerberos",
            "idle_timeout": "idle_timeout",
            "hide_special_share": "hide_special_share",
            "case_insensitive": "case_insensitive",
            "kerberos_ccache": "kerberos_ccache",
        },
        required_params=["repository", "host", "user", "share_name"],
        optional_params={"port": 445, "domain": "WORKGROUP", "path_prefix": ""},
    ),
)
class SMBProvider:
    """SMB provider registration"""

    config_class = SMBStorageConfig
    storage_class = SMBStorage
