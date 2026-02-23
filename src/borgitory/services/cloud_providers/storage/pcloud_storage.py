"""
pCloud storage implementation.

Uses rclone's pcloud backend (OAuth token + hostname). Paths are remote:path
(e.g. :pcloud:backups/borgitory). No bucket; path_prefix is the remote path.
"""

import asyncio
import json
from typing import AsyncGenerator, Callable, Dict, List, Optional, Union, cast
from pydantic import Field, field_validator

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.rclone_types import ConnectionTestResult, ProgressData

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider, RcloneMethodMapping


class PcloudStorageConfig(CloudStorageConfig):
    """Configuration for pCloud storage"""

    token: str = Field(..., min_length=1, description="OAuth token JSON blob from rclone config")
    hostname: str = Field(
        default="api.pcloud.com",
        min_length=1,
        description="pCloud API hostname (api.pcloud.com US, eapi.pcloud.com EU)",
    )
    root_folder_id: Optional[str] = Field(
        default=None,
        description="Root folder ID to use as root (optional, default d0)",
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Token is required")
        try:
            data = json.loads(v.strip())
            if not isinstance(data, dict) or "access_token" not in data:
                raise ValueError("Token must be valid JSON with 'access_token' key")
        except json.JSONDecodeError as e:
            raise ValueError(f"Token must be valid JSON: {e}") from e
        return v.strip()

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        if not v or not v.strip():
            return "api.pcloud.com"
        return v.strip().lower()


class PcloudStorage(CloudStorage):
    """
    pCloud storage implementation using rclone.
    """

    def __init__(
        self,
        config: PcloudStorageConfig,
        command_executor: CommandExecutorProtocol,
        file_service: FileServiceProtocol,
    ) -> None:
        self._config = config
        self._command_executor = command_executor
        self._file_service = file_service

    def _build_pcloud_flags(
        self,
        token: str,
        hostname: str = "api.pcloud.com",
        root_folder_id: Optional[str] = None,
    ) -> List[str]:
        flags = [
            "--pcloud-token",
            token,
            "--pcloud-hostname",
            hostname,
        ]
        if root_folder_id and root_folder_id.strip():
            flags.extend(["--pcloud-root-folder-id", root_folder_id.strip()])
        return flags

    async def upload_repository(
        self,
        repository_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[SyncEvent], None]] = None,
    ) -> None:
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting pCloud upload to {self._config.hostname}",
                )
            )

        try:
            final_status = None
            async for progress in self.sync_repository_to_pcloud(
                repository_path=repository_path,
                token=self._config.token,
                hostname=self._config.hostname,
                root_folder_id=self._config.root_folder_id,
                path_prefix=remote_path,
            ):
                if progress.get("type") == "completed":
                    final_status = progress.get("status")
                elif progress_callback and progress.get("type") == "log":
                    progress_callback(
                        SyncEvent(
                            type=SyncEventType.PROGRESS,
                            message=str(progress.get("message", "Uploading...")),
                            progress=float(progress.get("percentage", 0.0) or 0.0),
                        )
                    )

            if final_status == "failed":
                raise Exception("pCloud sync failed with non-zero exit code")

            if progress_callback:
                progress_callback(
                    SyncEvent(
                        type=SyncEventType.COMPLETED,
                        message="pCloud upload completed successfully",
                    )
                )

        except Exception as e:
            error_msg = f"pCloud upload failed: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        try:
            result = await self.test_pcloud_connection(
                token=self._config.token,
                hostname=self._config.hostname,
                root_folder_id=self._config.root_folder_id,
            )
            return result.get("status") == "success"
        except Exception:
            return False

    def get_connection_info(self) -> ConnectionInfo:
        token = self._config.token
        if len(token) > 12:
            masked = f"{token[:4]}***{token[-4:]}"
        else:
            masked = "***"
        return ConnectionInfo(
            provider="pcloud",
            details={
                "hostname": self._config.hostname,
                "root_folder_id": self._config.root_folder_id or "default",
                "token": masked,
            },
        )

    def get_sensitive_fields(self) -> list[str]:
        return ["token"]

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        hostname = config_dict.get("hostname", "api.pcloud.com")
        root_folder_id = config_dict.get("root_folder_id") or "default"
        provider_details = f"""
            <div><strong>Hostname:</strong> {hostname}</div>
            <div><strong>Root folder ID:</strong> {root_folder_id}</div>
        """.strip()
        return {
            "provider_name": "pCloud",
            "provider_details": provider_details,
        }

    @classmethod
    def get_rclone_mapping(cls) -> RcloneMethodMapping:
        return RcloneMethodMapping(
            sync_method="sync_repository_to_pcloud",
            test_method="test_pcloud_connection",
            parameter_mapping={
                "token": "token",
                "hostname": "hostname",
                "root_folder_id": "root_folder_id",
                "path_prefix": "path_prefix",
            },
            required_params=["repository", "token"],
            optional_params={
                "hostname": "api.pcloud.com",
                "root_folder_id": None,
                "path_prefix": "",
            },
        )

    async def sync_repository_to_pcloud(
        self,
        repository_path: str,
        token: str,
        hostname: str = "api.pcloud.com",
        root_folder_id: Optional[str] = None,
        path_prefix: str = "",
    ) -> AsyncGenerator[ProgressData, None]:
        remote_path = ":pcloud:"
        if path_prefix:
            prefix = path_prefix.strip("/").strip("\\")
            if prefix:
                remote_path = f":pcloud:{prefix}"

        command = [
            "rclone",
            "sync",
            repository_path,
            remote_path,
            "--progress",
            "--stats",
            "1s",
            "--verbose",
        ]
        command.extend(
            self._build_pcloud_flags(token, hostname, root_folder_id)
        )

        try:
            process = await self._command_executor.create_subprocess(
                command=command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            safe_cmd = " ".join(
                c if c != token else "***" for c in command
            )
            yield cast(
                ProgressData,
                {"type": "started", "command": safe_cmd, "pid": process.pid},
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

    async def test_pcloud_connection(
        self,
        token: str,
        hostname: str = "api.pcloud.com",
        root_folder_id: Optional[str] = None,
    ) -> ConnectionTestResult:
        command = ["rclone", "lsd", ":pcloud:", "--max-depth", "1", "--verbose"]
        command.extend(
            self._build_pcloud_flags(token, hostname, root_folder_id)
        )

        try:
            result = await self._command_executor.execute_command(
                command=command,
                timeout=30.0,
            )

            if result.success:
                return {
                    "status": "success",
                    "message": "Connection successful",
                    "output": result.stdout,
                    "details": {"read_test": "passed"},
                }
            return {
                "status": "failed",
                "message": result.stderr or "Connection failed",
                "output": result.stdout,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }

    def parse_rclone_progress(
        self, line: str
    ) -> Optional[Dict[str, Union[str, int, float]]]:
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
        for gen in async_generators:
            async for item in gen:
                yield item


@register_provider(
    name="pcloud",
    label="pCloud",
    description="pCloud storage",
    supports_encryption=True,
    supports_versioning=False,
    requires_credentials=True,
)
class PcloudProvider:
    """pCloud provider registration"""

    config_class = PcloudStorageConfig
    storage_class = PcloudStorage
