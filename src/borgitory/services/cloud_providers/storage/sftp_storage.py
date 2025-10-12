"""
SFTP cloud storage implementation.

This module provides SFTP-specific storage operations with clean separation
from business logic and easy testability.
"""

import asyncio
import os
import re
import subprocess
from typing import Callable, Dict, Optional, List, AsyncGenerator, Union, cast
from pydantic import Field, field_validator, model_validator
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncIterator

from borgitory.models.database import Repository
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.rclone_types import ConnectionTestResult, ProgressData

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
        self,
        config: SFTPStorageConfig,
        command_executor: CommandExecutorProtocol,
        file_service: FileServiceProtocol,
    ) -> None:
        """
        Initialize SFTP storage.

        Args:
            config: Validated SFTP configuration
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
        """Upload repository to SFTP server"""
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting SFTP upload to {self._config.host}:{self._config.remote_path}",
                )
            )

        try:
            repository_obj = Repository()
            repository_obj.path = repository_path

            async for progress in self.sync_repository_to_sftp(
                repository=repository_obj,
                host=self._config.host,
                username=self._config.username,
                remote_path=self._config.remote_path,
                port=self._config.port,
                password=self._config.password,
                private_key=self._config.private_key,
                path_prefix=remote_path,
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
                        error_msg = f"SFTP sync failed with return code {progress.get('return_code')}"
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
            result = await self.test_sftp_connection(
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

    @asynccontextmanager
    async def _build_sftp_flags(
        self,
        host: str,
        username: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> AsyncIterator[List[str]]:
        """Build SFTP configuration flags for rclone command"""
        flags = ["--sftp-host", host, "--sftp-user", username, "--sftp-port", str(port)]

        async with AsyncExitStack() as stack:
            if password:
                obscured_password = self._obscure_password(password)
                flags.extend(["--sftp-pass", obscured_password])
            elif private_key:
                key_file_path = await stack.enter_async_context(
                    self._file_service.create_temp_file(
                        suffix=".pem", content=private_key.encode("utf-8")
                    )
                )
                flags.extend(["--sftp-key-file", key_file_path])

            yield flags

    async def sync_repository_to_sftp(
        self,
        repository: Repository,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        path_prefix: str = "",
    ) -> AsyncGenerator[ProgressData, None]:
        """Sync a Borg repository to SFTP using Rclone with SFTP backend"""

        sftp_path = f":sftp:{remote_path}"
        if path_prefix:
            sftp_path = f"{sftp_path}/{path_prefix}"

        command = [
            "rclone",
            "sync",
            repository.path,
            sftp_path,
            "--progress",
            "--stats",
            "1s",
            "--verbose",
        ]

        try:
            async with self._build_sftp_flags(
                host, username, port, password, private_key
            ) as sftp_flags:
                command.extend(sftp_flags)

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
                            [c for c in command if not c.startswith("--sftp-pass")]
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
                            yield cast(
                                ProgressData, {"type": "progress", **progress_data}
                            )
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

    async def test_sftp_connection(
        self,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> ConnectionTestResult:
        """Test SFTP connection by listing remote directory"""
        try:
            sftp_path = f":sftp:{remote_path}"

            command = ["rclone", "lsd", sftp_path, "--max-depth", "1", "--verbose"]

            async with self._build_sftp_flags(
                host, username, port, password, private_key
            ) as sftp_flags:
                command.extend(sftp_flags)

                result = await self._command_executor.execute_command(
                    command=command, timeout=30.0
                )

                if result.success:
                    test_result = await self._test_sftp_write_permissions(
                        host, username, remote_path, port, password, private_key
                    )

                    if test_result.get("status") == "success":
                        return ConnectionTestResult(
                            status="success",
                            message="SFTP connection successful - remote directory accessible and writable",
                            output=result.stdout,
                            details={
                                "read_test": "passed",
                                "write_test": "passed",
                                "host": host,
                                "port": port,
                            },
                        )

                    else:
                        return ConnectionTestResult(
                            status="warning",
                            message=f"SFTP directory is readable but may have write permission issues: {test_result.get('message')}",
                            output=result.stdout,
                            details={
                                "read_test": "passed",
                                "write_test": "failed",
                                "host": host,
                                "port": port,
                            },
                        )

                else:
                    error_message = result.stderr.lower()
                    if "connection refused" in error_message:
                        return ConnectionTestResult(
                            status="failed",
                            message=f"Connection refused to {host}:{port} - check host and port",
                        )
                    elif (
                        "authentication failed" in error_message
                        or "permission denied" in error_message
                    ):
                        return ConnectionTestResult(
                            status="failed",
                            message="Authentication failed - check username, password, or SSH key",
                        )
                    elif "no such file or directory" in error_message:
                        return ConnectionTestResult(
                            status="failed",
                            message=f"Remote path '{remote_path}' does not exist",
                        )
                    else:
                        return ConnectionTestResult(
                            status="failed",
                            message=f"SFTP connection failed: {result.stderr}",
                        )

        except Exception as e:
            return ConnectionTestResult(
                status="error",
                message=f"Test failed with exception: {str(e)}",
            )

    async def _test_sftp_write_permissions(
        self,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> ConnectionTestResult:
        """Test write permissions by creating and deleting a small test file"""
        key_file_path = None
        temp_file_path = None

        try:
            from borgitory.utils.datetime_utils import now_utc

            test_content = f"borgitory-test-{now_utc().isoformat()}"
            test_filename = f"borgitory-test-{now_utc().strftime('%Y%m%d-%H%M%S')}.txt"

            async with self._file_service.create_temp_file(
                suffix=".txt", content=test_content.encode("utf-8")
            ) as temp_file_path:
                sftp_path = f":sftp:{remote_path}/{test_filename}"

                upload_command = ["rclone", "copy", temp_file_path, sftp_path]

                async with self._build_sftp_flags(
                    host, username, port, password, private_key
                ) as sftp_flags:
                    upload_command.extend(sftp_flags)

                    if "--sftp-key-file" in sftp_flags:
                        key_file_idx = sftp_flags.index("--sftp-key-file")
                        if key_file_idx + 1 < len(sftp_flags):
                            key_file_path = sftp_flags[key_file_idx + 1]

                    upload_result = await self._command_executor.execute_command(
                        command=upload_command, timeout=30.0
                    )

                    if upload_result.success:
                        delete_command = ["rclone", "delete", sftp_path]
                        delete_command.extend(sftp_flags)

                        await self._command_executor.execute_command(
                            command=delete_command, timeout=30.0
                        )

                        return {
                            "status": "success",
                            "message": "Write permissions verified",
                        }
                    else:
                        return {
                            "status": "failed",
                            "message": f"Cannot write to SFTP directory: {upload_result.stderr}",
                        }

        except Exception as e:
            return {"status": "failed", "message": f"Write test failed: {str(e)}"}
        finally:
            if key_file_path:
                try:
                    os.unlink(key_file_path)
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
