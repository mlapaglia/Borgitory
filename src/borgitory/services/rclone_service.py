import asyncio
import logging
import subprocess
import tempfile
import os
import time
from typing import (
    AsyncGenerator,
    Dict,
    Optional,
    Callable,
    List,
    Union,
    cast,
    TypedDict,
    Literal,
)

from borgitory.models.database import Repository
from borgitory.utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)


# Type definitions for cloud provider configurations
class S3Config(TypedDict):
    """Type definition for S3 provider configuration"""

    provider: Literal["s3"]
    bucket_name: str
    access_key_id: str
    secret_access_key: str
    region: str
    endpoint_url: Optional[str]
    storage_class: str
    path_prefix: str


class SFTPConfig(TypedDict):
    """Type definition for SFTP provider configuration"""

    provider: Literal["sftp"]
    host: str
    username: str
    port: int
    password: Optional[str]
    private_key: Optional[str]
    remote_path: str
    path_prefix: str


class SMBConfig(TypedDict):
    """Type definition for SMB provider configuration"""

    provider: Literal["smb"]
    host: str
    user: str
    share_name: str
    password: Optional[str]
    port: int
    domain: str
    spn: Optional[str]
    use_kerberos: bool
    idle_timeout: str
    hide_special_share: bool
    case_insensitive: bool
    kerberos_ccache: Optional[str]
    path_prefix: str


# Union type for all cloud provider configurations
CloudProviderConfig = Union[S3Config, SFTPConfig, SMBConfig]


class ConnectionTestResult(TypedDict, total=False):
    """Type definition for connection test results"""

    status: Literal["success", "failed", "warning", "error"]
    message: str
    output: Optional[str]
    details: Optional[Dict[str, Union[str, int, bool, None]]]
    can_write: Optional[bool]


class SyncResult(TypedDict, total=False):
    """Type definition for sync operation results"""

    success: bool
    error: Optional[str]
    stats: Optional[Dict[str, Union[str, int, float]]]


class ProgressData(TypedDict, total=False):
    """Type definition for progress data from rclone operations"""

    type: str
    transferred: Optional[str]
    total: Optional[str]
    percentage: Optional[float]
    speed: Optional[str]
    eta: Optional[str]
    command: Optional[str]
    pid: Optional[int]
    return_code: Optional[int]
    status: Optional[str]
    message: Optional[str]
    stream: Optional[str]


class RcloneService:
    def __init__(self) -> None:
        pass  # No longer need config file management

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
            "AWS",
            "--s3-region",
            region,
            "--s3-storage-class",
            storage_class,
        ]

        # Add endpoint URL if specified (for S3-compatible services)
        if endpoint_url:
            flags.extend(["--s3-endpoint", endpoint_url])

        return flags

    async def sync_repository_to_s3(
        self,
        repository: Repository,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        path_prefix: str = "",
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        storage_class: str = "STANDARD",
    ) -> AsyncGenerator[ProgressData, None]:
        """Sync a Borg repository to S3 using Rclone with direct S3 backend"""

        # Build S3 path
        s3_path = f":s3:{bucket_name}"
        if path_prefix:
            s3_path = f"{s3_path}/{path_prefix}"

        # Build rclone command with S3 backend flags
        command = [
            "rclone",
            "sync",
            repository.path,
            s3_path,
            "--progress",
            "--stats",
            "1s",
            "--verbose",
        ]

        # Add S3 configuration flags
        s3_flags = self._build_s3_flags(
            access_key_id, secret_access_key, region, endpoint_url, storage_class
        )
        command.extend(s3_flags)

        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode("utf-8")
            stderr_text = stderr.decode("utf-8")

            if process.returncode == 0:
                test_result = await self._test_s3_write_permissions(
                    access_key_id, secret_access_key, bucket_name
                )

                if test_result.get("status") == "success":
                    return {
                        "status": "success",
                        "message": "Connection successful - bucket accessible and writable",
                        "output": stdout_text,
                        "details": {"read_test": "passed", "write_test": "passed"},
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"Bucket is readable but may have write permission issues: {test_result.get('message', 'Unknown error')}",
                        "output": stdout_text,
                        "details": {"read_test": "passed", "write_test": "failed"},
                    }
            else:
                error_message = stderr_text.lower()
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
                        "message": f"Connection failed: {stderr_text}",
                    }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Test failed with exception: {str(e)}",
            }

    async def _test_s3_write_permissions(
        self, access_key_id: str, secret_access_key: str, bucket_name: str
    ) -> ConnectionTestResult:
        """Test write permissions by creating and deleting a small test file"""
        try:
            test_content = f"borgitory-test-{now_utc().isoformat()}"
            test_filename = f"borgitory-test-{now_utc().strftime('%Y%m%d-%H%M%S')}.txt"

            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name

            try:
                s3_path = f":s3:{bucket_name}/{test_filename}"

                upload_command = ["rclone", "copy", temp_file_path, s3_path]

                s3_flags = self._build_s3_flags(access_key_id, secret_access_key)
                upload_command.extend(s3_flags)

                process = await asyncio.create_subprocess_exec(
                    *upload_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    delete_command = ["rclone", "delete", s3_path]
                    delete_command.extend(s3_flags)

                    delete_process = await asyncio.create_subprocess_exec(
                        *delete_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    await delete_process.communicate()

                    return {
                        "status": "success",
                        "message": "Write permissions verified",
                    }
                else:
                    return {
                        "status": "failed",
                        "message": f"Cannot write to bucket: {stderr.decode('utf-8')}",
                    }

            finally:
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

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

    def _build_sftp_flags(
        self,
        host: str,
        username: str,
        port: int = 22,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> List[str]:
        """Build SFTP configuration flags for rclone command"""
        flags = ["--sftp-host", host, "--sftp-user", username, "--sftp-port", str(port)]

        if password:
            obscured_password = self._obscure_password(password)
            flags.extend(["--sftp-pass", obscured_password])
        elif private_key:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".pem"
            ) as key_file:
                key_file.write(private_key)
                key_file_path = key_file.name

            flags.extend(["--sftp-key-file", key_file_path])

        return flags

    def _obscure_password(self, password: str) -> str:
        """Obscure password using rclone's method"""

        try:
            # Use rclone obscure command to properly encode the password
            result = subprocess.run(
                ["rclone", "obscure", password],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.error(f"rclone obscure failed: {result.stderr}")
                return password

        except Exception as e:
            logger.error(f"Failed to obscure password: {e}")
            return password

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

        # Build SFTP path
        sftp_path = f":sftp:{remote_path}"
        if path_prefix:
            sftp_path = f"{sftp_path}/{path_prefix}"

        # Build rclone command with SFTP backend flags
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

        # Add SFTP configuration flags
        sftp_flags = self._build_sftp_flags(host, username, port, password, private_key)
        command.extend(sftp_flags)

        key_file_path = None
        try:
            if "--sftp-key-file" in sftp_flags:
                key_file_idx = sftp_flags.index("--sftp-key-file")
                if key_file_idx + 1 < len(sftp_flags):
                    key_file_path = sftp_flags[key_file_idx + 1]

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            yield cast(
                ProgressData,
                {
                    "type": "started",
                    "command": " ".join(
                        [c for c in command if not c.startswith("--sftp-pass")]
                    ),  # Hide password
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
        finally:
            if key_file_path:
                try:
                    os.unlink(key_file_path)
                except OSError:
                    pass

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
        key_file_path = None
        try:
            sftp_path = f":sftp:{remote_path}"

            command = ["rclone", "lsd", sftp_path, "--max-depth", "1", "--verbose"]

            sftp_flags = self._build_sftp_flags(
                host, username, port, password, private_key
            )
            command.extend(sftp_flags)

            if "--sftp-key-file" in sftp_flags:
                key_file_idx = sftp_flags.index("--sftp-key-file")
                if key_file_idx + 1 < len(sftp_flags):
                    key_file_path = sftp_flags[key_file_idx + 1]

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode("utf-8")
            stderr_text = stderr.decode("utf-8")

            if process.returncode == 0:
                test_result = await self._test_sftp_write_permissions(
                    host, username, remote_path, port, password, private_key
                )

                if test_result.get("status") == "success":
                    return {
                        "status": "success",
                        "message": "SFTP connection successful - remote directory accessible and writable",
                        "output": stdout_text,
                        "details": {
                            "read_test": "passed",
                            "write_test": "passed",
                            "host": host,
                            "port": port,
                        },
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"SFTP directory is readable but may have write permission issues: {test_result['message']}",
                        "output": stdout_text,
                        "details": {
                            "read_test": "passed",
                            "write_test": "failed",
                            "host": host,
                            "port": port,
                        },
                    }
            else:
                error_message = stderr_text.lower()
                if "connection refused" in error_message:
                    return {
                        "status": "failed",
                        "message": f"Connection refused to {host}:{port} - check host and port",
                    }
                elif (
                    "authentication failed" in error_message
                    or "permission denied" in error_message
                ):
                    return {
                        "status": "failed",
                        "message": "Authentication failed - check username, password, or SSH key",
                    }
                elif "no such file or directory" in error_message:
                    return {
                        "status": "failed",
                        "message": f"Remote path '{remote_path}' does not exist",
                    }
                else:
                    return {
                        "status": "failed",
                        "message": f"SFTP connection failed: {stderr_text}",
                    }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Test failed with exception: {str(e)}",
            }
        finally:
            if key_file_path:
                try:
                    os.unlink(key_file_path)
                except OSError:
                    pass

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

            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name

            try:
                sftp_path = f":sftp:{remote_path}/{test_filename}"

                upload_command = ["rclone", "copy", temp_file_path, sftp_path]

                sftp_flags = self._build_sftp_flags(
                    host, username, port, password, private_key
                )
                upload_command.extend(sftp_flags)

                if "--sftp-key-file" in sftp_flags:
                    key_file_idx = sftp_flags.index("--sftp-key-file")
                    if key_file_idx + 1 < len(sftp_flags):
                        key_file_path = sftp_flags[key_file_idx + 1]

                process = await asyncio.create_subprocess_exec(
                    *upload_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    delete_command = ["rclone", "delete", sftp_path]
                    delete_command.extend(sftp_flags)

                    delete_process = await asyncio.create_subprocess_exec(
                        *delete_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    await delete_process.communicate()

                    return {
                        "status": "success",
                        "message": "Write permissions verified",
                    }
                else:
                    return {
                        "status": "failed",
                        "message": f"Cannot write to SFTP directory: {stderr.decode('utf-8')}",
                    }

            finally:
                if temp_file_path:
                    try:
                        os.unlink(temp_file_path)
                    except OSError:
                        pass

        except Exception as e:
            return {"status": "failed", "message": f"Write test failed: {str(e)}"}
        finally:
            if key_file_path:
                try:
                    os.unlink(key_file_path)
                except OSError:
                    pass

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

    async def sync_repository(
        self,
        source_path: str,
        remote_path: str,
        config: CloudProviderConfig,
        progress_callback: Optional[Callable[[ProgressData], None]] = None,
    ) -> SyncResult:
        """
        Generic sync repository method that delegates to provider-specific methods
        based on the cloud sync configuration.
        """
        try:
            provider = str(config.get("provider", "")).lower()

            if provider == "s3":
                bucket_name = config.get("bucket_name")
                access_key_id = config.get("access_key_id")
                secret_access_key = config.get("secret_access_key")
                path_prefix = str(config.get("path_prefix", ""))

                if not all([bucket_name, access_key_id, secret_access_key]):
                    return {
                        "success": False,
                        "error": "Missing required S3 configuration (bucket_name, access_key_id, secret_access_key)",
                    }

                mock_repo = Repository()
                mock_repo.path = source_path

                stats: Dict[str, Union[str, int, float]] = {}
                async for progress_data in self.sync_repository_to_s3(
                    repository=mock_repo,
                    access_key_id=str(access_key_id),
                    secret_access_key=str(secret_access_key),
                    bucket_name=str(bucket_name),
                    path_prefix=path_prefix,
                ):
                    if progress_callback:
                        progress_callback(progress_data)

                    if progress_data.get("type") == "completed":
                        if progress_data.get("status") == "success":
                            return {"success": True, "stats": stats}
                        else:
                            return {
                                "success": False,
                                "error": f"Rclone process failed with return code {progress_data.get('return_code')}",
                            }
                    elif progress_data.get("type") == "progress":
                        # Only update with numeric/string values that stats can handle
                        for key, value in progress_data.items():
                            if key != "type" and isinstance(value, (str, int, float)):
                                stats[key] = value
                    elif progress_data.get("type") == "error":
                        return {
                            "success": False,
                            "error": progress_data.get("message", "Unknown error"),
                        }

                return {
                    "success": False,
                    "error": "Sync process completed without final status",
                }

            elif provider == "sftp":
                host = config.get("host")
                username = config.get("username")
                port_value = config.get("port", 22)
                port = int(port_value) if isinstance(port_value, (int, str)) else 22
                password = (
                    str(config.get("password")) if config.get("password") else None
                )
                private_key = (
                    str(config.get("private_key"))
                    if config.get("private_key")
                    else None
                )
                path_prefix = str(config.get("path_prefix", ""))

                if not all([host, username]):
                    return {
                        "success": False,
                        "error": "Missing required SFTP configuration (host, username)",
                    }

                if not password and not private_key:
                    return {
                        "success": False,
                        "error": "Either password or private_key must be provided for SFTP",
                    }

                mock_repo = Repository()
                mock_repo.path = source_path

                sftp_stats: Dict[str, Union[str, int, float]] = {}
                async for progress_data in self.sync_repository_to_sftp(
                    repository=mock_repo,
                    host=str(host),
                    username=str(username),
                    remote_path=remote_path.replace(
                        f"{config.get('remote_name', '')}:", ""
                    ),
                    port=port,
                    password=password,
                    private_key=private_key,
                    path_prefix=path_prefix,
                ):
                    if progress_callback:
                        progress_callback(progress_data)

                    if progress_data.get("type") == "completed":
                        if progress_data.get("status") == "success":
                            return {"success": True, "stats": sftp_stats}
                        else:
                            return {
                                "success": False,
                                "error": f"Rclone process failed with return code {progress_data.get('return_code')}",
                            }
                    elif progress_data.get("type") == "progress":
                        # Only update with numeric/string values that stats can handle
                        for key, value in progress_data.items():
                            if key != "type" and isinstance(value, (str, int, float)):
                                sftp_stats[key] = value
                    elif progress_data.get("type") == "error":
                        return {
                            "success": False,
                            "error": progress_data.get("message", "Unknown error"),
                        }

                return {
                    "success": False,
                    "error": "Sync process completed without final status",
                }

            else:
                return {
                    "success": False,
                    "error": f"Unsupported cloud provider: {provider}",
                }

        except Exception as e:
            logger.error(f"Error in sync_repository: {e}")
            return {"success": False, "error": str(e)}

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
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode("utf-8")
            stderr_text = stderr.decode("utf-8")

            logger.info(f"SMB test command return code: {process.returncode}")
            if stderr_text.strip():
                logger.info(f"SMB test stderr: {stderr_text.strip()}")
            if stdout_text.strip():
                logger.info(f"SMB test stdout: {stdout_text.strip()}")

            if process.returncode == 0:
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
                            "stdout": stdout_text,
                        },
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"Connected to SMB share but write test failed: {test_result.get('message', 'Unknown error')}",
                        "details": {
                            "can_list": True,
                            "can_write": False,
                            "stdout": stdout_text,
                            "write_error": test_result.get("message"),
                        },
                    }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to connect to SMB share {share_name} on {host}",
                    "details": {
                        "return_code": process.returncode,
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                    },
                }

        except Exception as e:
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

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                delete_command = [
                    "rclone",
                    "deletefile",
                    f"{remote_test_path}/{test_filename}",
                    "--verbose",
                ]
                delete_command.extend(smb_flags)

                delete_process = await asyncio.create_subprocess_exec(
                    *delete_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await delete_process.communicate()

                return {
                    "status": "success",
                    "can_write": True,
                    "message": "Write permissions confirmed",
                }
            else:
                return {
                    "status": "error",
                    "can_write": False,
                    "message": f"Write test failed: {stderr.decode('utf-8')}",
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

    # Generic dispatcher methods using registry-based mapping
    async def sync_repository_to_provider(
        self,
        provider: str,
        repository: Repository,
        **provider_config: Union[str, int, bool, None],
    ) -> AsyncGenerator[ProgressData, None]:
        """
        Truly generic provider sync dispatcher using registry.

        Args:
            provider: Provider name (e.g., "s3", "sftp", "smb")
            repository: Repository object to sync
            **provider_config: Provider-specific configuration parameters

        Yields:
            Progress dictionaries from the underlying rclone method

        Raises:
            ValueError: If provider is unknown or has no rclone mapping
        """
        from .cloud_providers.registry import get_metadata

        # Get rclone mapping from registry
        metadata = get_metadata(provider)
        if not metadata or not metadata.rclone_mapping:
            raise ValueError(f"Provider '{provider}' has no rclone mapping configured")

        mapping = metadata.rclone_mapping

        # Get the rclone method
        sync_method = getattr(self, mapping.sync_method, None)
        if not sync_method:
            raise ValueError(f"Rclone method '{mapping.sync_method}' not found")

        # Map parameters from borgitory.config to rclone method parameters
        rclone_params: Dict[str, Union[str, int, bool, Repository, None]] = {
            "repository": repository
        }

        # Apply parameter mapping
        for config_field, rclone_param in mapping.parameter_mapping.items():
            if config_field in provider_config:
                rclone_params[rclone_param] = provider_config[config_field]
            elif config_field == "repository" and config_field in rclone_params:
                # Handle repository -> repository_path conversion
                if rclone_param == "repository_path":
                    rclone_params[rclone_param] = repository.path
                else:
                    rclone_params[rclone_param] = repository

        # Add optional parameters with defaults
        if mapping.optional_params:
            for param, default_value in mapping.optional_params.items():
                if param not in rclone_params:
                    value = provider_config.get(param, default_value)
                    if isinstance(value, (str, int, bool, type(None))):
                        rclone_params[param] = value

        # Remove the original repository key if it was mapped to a different name
        if (
            "repository" in mapping.parameter_mapping
            and "repository" in rclone_params
            and mapping.parameter_mapping["repository"] != "repository"
        ):
            del rclone_params["repository"]

        # Validate required parameters (check mapped parameter names)
        missing_params = []
        for required_param in mapping.required_params:
            # Check if the required param was mapped to a different name
            mapped_param = mapping.parameter_mapping.get(required_param, required_param)
            if mapped_param not in rclone_params:
                missing_params.append(required_param)

        if missing_params:
            raise ValueError(
                f"Missing required parameters for {provider}: {missing_params}"
            )

        # Call the method and yield results
        async for result in sync_method(**rclone_params):
            yield result

    async def test_provider_connection(
        self, provider: str, **provider_config: Union[str, int, bool, None]
    ) -> ConnectionTestResult:
        """
        Generic provider connection test dispatcher using registry.

        Args:
            provider: Provider name (e.g., "s3", "sftp", "smb")
            **provider_config: Provider-specific configuration parameters

        Returns:
            Dictionary with connection test results

        Raises:
            ValueError: If provider is unknown or has no rclone mapping
        """
        from .cloud_providers.registry import get_metadata

        # Get rclone mapping from registry
        metadata = get_metadata(provider)
        if not metadata or not metadata.rclone_mapping:
            raise ValueError(f"Provider '{provider}' has no rclone mapping configured")

        mapping = metadata.rclone_mapping

        # Get the rclone test method
        test_method = getattr(self, mapping.test_method, None)
        if not test_method:
            raise ValueError(f"Rclone test method '{mapping.test_method}' not found")

        # Map parameters from borgitory.config to rclone method parameters
        rclone_params: Dict[str, Union[str, int, bool, None]] = {}

        # Apply parameter mapping
        for config_field, rclone_param in mapping.parameter_mapping.items():
            if config_field in provider_config:
                rclone_params[rclone_param] = provider_config[config_field]

        # Add optional parameters with defaults (excluding repository and path_prefix for connection tests)
        if mapping.optional_params:
            for param, default_value in mapping.optional_params.items():
                if param not in ["path_prefix"] and param not in rclone_params:
                    value = provider_config.get(param, default_value)
                    if isinstance(value, (str, int, bool, type(None))):
                        rclone_params[param] = value

        # Validate required parameters (excluding repository for connection tests)
        test_required_params = [p for p in mapping.required_params if p != "repository"]
        missing_params = [p for p in test_required_params if p not in rclone_params]
        if missing_params:
            raise ValueError(
                f"Missing required parameters for {provider} connection test: {missing_params}"
            )

        # Call the test method
        result = await test_method(**rclone_params)
        return cast(ConnectionTestResult, result)
