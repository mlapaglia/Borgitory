"""
Amazon S3 compatible cloud storage implementation.

This module provides S3-specific storage operations with clean separation
from business logic and easy testability.
"""

import asyncio
import re
from enum import Enum
from typing import AsyncGenerator, Callable, Dict, List, Optional, Union, cast
from pydantic import Field, field_validator, model_validator

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.rclone_types import ConnectionTestResult, ProgressData
from borgitory.utils.datetime_utils import now_utc

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider, RcloneMethodMapping


class S3Provider(str, Enum):
    """S3-compatible storage providers"""

    AWS = "AWS"
    ALIBABA = "Alibaba"
    ARVAN_CLOUD = "ArvanCloud"
    BACKBLAZE = "Backblaze"
    CEPH = "Ceph"
    CHINA_MOBILE = "ChinaMobile"
    CLOUDFLARE = "Cloudflare"
    DIGITALOCEAN = "DigitalOcean"
    DREAMHOST = "Dreamhost"
    EXABA = "Exaba"
    FILELU = "FileLu"
    FLASHBLADE = "FlashBlade"
    GCS = "GCS"
    HETZNER = "Hetzner"
    HUAWEI_OBS = "HuaweiOBS"
    IBM_COS = "IBMCOS"
    IDRIVE = "IDrive"
    INTERCOLO = "Intercolo"
    IONOS = "IONOS"
    LYVE_CLOUD = "LyveCloud"
    LEVIIA = "Leviia"
    LIARA = "Liara"
    LINODE = "Linode"
    MAGALU = "Magalu"
    MEGA = "Mega"
    MINIO = "Minio"
    NETEASE = "Netease"
    OUTSCALE = "Outscale"
    OVH_CLOUD = "OVHcloud"
    PETABOX = "Petabox"
    RABATA = "Rabata"
    RACKCORP = "RackCorp"
    RCLONE = "Rclone"
    SCALEWAY = "Scaleway"
    SEAWEEDFS = "SeaweedFS"
    SELECTEL = "Selectel"
    SPECTRA_LOGIC = "SpectraLogic"
    STACKPATH = "StackPath"
    STORJ = "Storj"
    SYNOLOGY = "Synology"
    TENCENT_COS = "TencentCOS"
    WASABI = "Wasabi"
    QINIU = "Qiniu"
    ZATA = "Zata"
    OTHER = "Other"


class S3StorageConfig(CloudStorageConfig):
    """Configuration for S3-compatible storage"""

    provider_type: S3Provider = Field(default=S3Provider.AWS)
    bucket_name: str = Field(..., min_length=3, max_length=63)
    access_key: str = Field(..., min_length=16, max_length=128)
    secret_key: str = Field(..., min_length=16, max_length=128)
    region: str = Field(default="us-east-1")
    endpoint_url: Optional[str] = None
    storage_class: str = Field(default="STANDARD")

    @model_validator(mode="after")
    def validate_credentials(self) -> "S3StorageConfig":
        """Validate credentials based on provider"""
        if not self.access_key.startswith("AKIA"):
            raise ValueError("AWS Access Key ID must start with 'AKIA'")
        if len(self.access_key) != 20:
            raise ValueError("AWS Access Key ID must be exactly 20 characters long")
        if not self.access_key.isalnum():
            raise ValueError(
                "AWS Access Key ID must contain only alphanumeric characters"
            )
        self.access_key = self.access_key.upper()

        if len(self.secret_key) != 40:
            raise ValueError("AWS Secret Access Key must be exactly 40 characters long")
        if not re.match(r"^[A-Za-z0-9+/=]+$", self.secret_key):
            raise ValueError("AWS Secret Access Key contains invalid characters")

        return self

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

    @model_validator(mode="after")
    def validate_storage_class_for_provider(self) -> "S3StorageConfig":
        """Validate storage class is supported by the selected provider"""
        from .s3_provider_config import S3ProviderConfig

        valid_classes = S3ProviderConfig.get_storage_classes(self.provider_type)
        storage_class_upper = self.storage_class.upper()

        if storage_class_upper not in valid_classes:
            raise ValueError(
                f"Storage class '{self.storage_class}' is not supported by {self.provider_type.value}. "
                f"Valid options: {', '.join(valid_classes)}"
            )

        self.storage_class = storage_class_upper
        return self


class S3Storage(CloudStorage):
    """
    Amazon S3 compatible cloud storage implementation.

    This class handles S3-specific operations while maintaining the clean
    CloudStorage interface for easy testing and integration.
    """

    def __init__(
        self,
        config: S3StorageConfig,
        command_executor: CommandExecutorProtocol,
        file_service: FileServiceProtocol,
    ) -> None:
        """
        Initialize S3 storage.

        Args:
            config: Validated S3 configuration
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
        """Upload repository to S3-compatible storage"""
        if progress_callback:
            provider_name = self._config.provider_type.value
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting {provider_name} upload to bucket {self._config.bucket_name}",
                )
            )

        try:
            final_status = None
            async for progress in self.sync_repository_to_s3(
                repository_path=repository_path,
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
                raise Exception(
                    f"{self._config.provider_type.value} sync failed with non-zero exit code"
                )

            if progress_callback:
                progress_callback(
                    SyncEvent(
                        type=SyncEventType.COMPLETED,
                        message=f"{self._config.provider_type.value} upload completed successfully",
                    )
                )

        except Exception as e:
            error_msg = f"{self._config.provider_type.value} upload failed: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        """Test S3 connection"""
        try:
            result = await self.test_s3_connection(
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
                "provider_type": self._config.provider_type.value,
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
        provider_type = config_dict.get("provider_type", "AWS")
        bucket_name = config_dict.get("bucket_name", "Unknown")
        region = config_dict.get("region", "us-east-1")
        storage_class = config_dict.get("storage_class", "STANDARD")
        endpoint = config_dict.get("endpoint_url", None)

        provider_details_parts = [
            f"<div><strong>Provider Type:</strong> {provider_type}</div>",
            f"<div><strong>Bucket:</strong> {bucket_name}</div>",
            f"<div><strong>Region:</strong> {region}</div>",
            f"<div><strong>Storage Class:</strong> {storage_class}</div>",
        ]

        if endpoint:
            provider_details_parts.append(
                f"<div><strong>Endpoint:</strong> {endpoint}</div>"
            )

        provider_details = "\n".join(provider_details_parts)
        provider_label = "S3-Compatible"

        return {"provider_name": provider_label, "provider_details": provider_details}

    @classmethod
    def get_rclone_mapping(cls) -> RcloneMethodMapping:
        """Define rclone parameter mapping for S3"""
        return RcloneMethodMapping(
            sync_method="sync_repository_to_s3",
            test_method="test_s3_connection",
            parameter_mapping={
                "provider_type": "provider_type",
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
            optional_params={
                "path_prefix": "",
                "region": "us-east-1",
                "provider_type": "AWS",
            },
        )

    def _build_s3_flags(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        storage_class: str = "STANDARD",
    ) -> List[str]:
        """Build S3 configuration flags for rclone command"""
        flags = [
            "--s3-access-key-id",
            access_key_id,
            "--s3-secret-access-key",
            secret_access_key,
            "--s3-provider",
            self._config.provider_type.value,
            "--s3-region",
            region,
            "--s3-storage-class",
            storage_class,
        ]

        if endpoint_url:
            flags.extend(["--s3-endpoint", endpoint_url])

        return flags

    async def sync_repository_to_s3(
        self,
        repository_path: str,
        path_prefix: str = "",
    ) -> AsyncGenerator[ProgressData, None]:
        """Sync a Borg repository to S3 using Rclone with direct S3 backend"""

        # Build S3 path
        s3_path = f":s3:{self._config.bucket_name}"
        if path_prefix:
            s3_path = f"{s3_path}/{path_prefix}"

        # Build rclone command with S3 backend flags
        command = [
            "rclone",
            "sync",
            repository_path,
            s3_path,
            "--progress",
            "--stats",
            "1s",
            "--verbose",
        ]

        # Add S3 configuration flags
        s3_flags = self._build_s3_flags(
            self._config.access_key,
            self._config.secret_key,
            self._config.region,
            self._config.endpoint_url,
            self._config.storage_class,
        )
        command.extend(s3_flags)

        try:
            process = await self._command_executor.create_subprocess(
                command=command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            yield cast(
                ProgressData,
                {"type": "started", "command": " ".join(command), "pid": process.pid},
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

    async def test_s3_connection(
        self,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        storage_class: str = "STANDARD",
    ) -> ConnectionTestResult:
        """Test S3 connection by checking bucket access"""
        try:
            s3_path = f":s3:{bucket_name}"

            # Build rclone command with S3 backend flags
            command = [
                "rclone",
                "lsd",
                s3_path,
                "--max-depth",
                "1",
                "--verbose",
            ]

            # Add S3 configuration flags
            s3_flags = self._build_s3_flags(
                access_key_id, secret_access_key, region, endpoint_url, storage_class
            )
            command.extend(s3_flags)

            result = await self._command_executor.execute_command(
                command=command,
                timeout=30.0,  # Reasonable timeout for connection test
            )

            if result.success:
                test_result = await self._test_s3_write_permissions()

                if test_result.get("status") == "success":
                    return {
                        "status": "success",
                        "message": "Connection successful - bucket accessible and writable",
                        "output": result.stdout,
                        "details": {"read_test": "passed", "write_test": "passed"},
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"Bucket is readable but may have write permission issues: {test_result.get('message', 'Unknown error')}",
                        "output": result.stdout,
                        "details": {"read_test": "passed", "write_test": "failed"},
                    }
            else:
                error_message = result.stderr.lower()
                if "no such bucket" in error_message or "nosuchbucket" in error_message:
                    return {
                        "status": "failed",
                        "message": f"Bucket '{bucket_name}' does not exist or is not accessible",
                    }
                elif (
                    "invalid access key" in error_message
                    or "access denied" in error_message
                ):
                    return {
                        "status": "failed",
                        "message": "Access denied - check your AWS credentials",
                    }
                else:
                    return {
                        "status": "failed",
                        "message": f"Connection failed: {result.stderr}",
                    }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Test failed with exception: {str(e)}",
            }

    async def _test_s3_write_permissions(self) -> ConnectionTestResult:
        """Test write permissions by creating and deleting a small test file"""
        try:
            test_content = f"borgitory-test-{now_utc().isoformat()}"
            test_filename = f"borgitory-test-{now_utc().strftime('%Y%m%d-%H%M%S')}.txt"

            async with self._file_service.create_temp_file(
                suffix=".txt", content=test_content.encode("utf-8")
            ) as temp_file_path:
                s3_path = f":s3:{self._config.bucket_name}/{test_filename}"

                upload_command = ["rclone", "copy", temp_file_path, s3_path]

                s3_flags = self._build_s3_flags(
                    self._config.access_key, self._config.secret_key
                )
                upload_command.extend(s3_flags)

                upload_result = await self._command_executor.execute_command(
                    command=upload_command, timeout=30.0
                )

                if upload_result.success:
                    delete_command = ["rclone", "delete", s3_path]
                    delete_command.extend(s3_flags)

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
                        "message": f"Cannot write to bucket: {upload_result.stderr}",
                    }

        except Exception as e:
            return {"status": "failed", "message": f"Write test failed: {str(e)}"}

    def parse_rclone_progress(
        self, line: str
    ) -> Optional[Dict[str, Union[str, int, float]]]:
        """Parse Rclone progress output"""
        # Look for progress statistics
        if "Transferred:" in line:
            try:
                # Example: "Transferred:   	  123.45 MiByte / 456.78 MiByte, 27%, 12.34 MiByte/s, ETA 1m23s"
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

        # Look for ETA information
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
    name="s3",
    label="S3-Compatible Storage",
    description="Amazon S3-compatible storage providers",
    supports_encryption=True,
    supports_versioning=True,
    requires_credentials=True,
    rclone_mapping=RcloneMethodMapping(
        sync_method="sync_repository_to_s3",
        test_method="test_s3_connection",
        parameter_mapping={
            "provider_type": "provider_type",
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
        optional_params={
            "path_prefix": "",
            "region": "us-east-1",
            "provider_type": "AWS",
        },
    ),
)
class S3ProviderRegistration:
    """S3 provider registration"""

    config_class = S3StorageConfig
    storage_class = S3Storage
