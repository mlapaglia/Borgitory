import asyncio
import logging
import subprocess
from typing import AsyncGenerator, Dict, Optional

from models.database import Repository

logger = logging.getLogger(__name__)


class RcloneService:
    def __init__(self):
        pass  # No longer need config file management

    def _build_s3_flags(self, access_key_id: str, secret_access_key: str) -> list:
        """Build S3 configuration flags for rclone command"""
        flags = [
            "--s3-access-key-id",
            access_key_id,
            "--s3-secret-access-key",
            secret_access_key,
            "--s3-provider",
            "AWS",
        ]

        return flags

    async def sync_repository_to_s3(
        self,
        repository: Repository,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        path_prefix: str = "",
    ) -> AsyncGenerator[Dict, None]:
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
        s3_flags = self._build_s3_flags(access_key_id, secret_access_key)
        command.extend(s3_flags)

        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            yield {"type": "started", "command": " ".join(command), "pid": process.pid}

            # Read stdout and stderr concurrently
            async def read_stream(stream, stream_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break

                    decoded_line = line.decode("utf-8").strip()
                    progress_data = self.parse_rclone_progress(decoded_line)

                    if progress_data:
                        yield {"type": "progress", **progress_data}
                    else:
                        yield {
                            "type": "log",
                            "stream": stream_type,
                            "message": decoded_line,
                        }

            # Stream both stdout and stderr
            async for item in self._merge_async_generators(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
            ):
                yield item

            # Wait for process to complete
            return_code = await process.wait()

            yield {
                "type": "completed",
                "return_code": return_code,
                "status": "success" if return_code == 0 else "failed",
            }

        except Exception as e:
            yield {"type": "error", "message": str(e)}

    async def test_s3_connection(
        self,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> Dict:
        """Test S3 connection by checking bucket access"""
        try:
            # Test 1: Check if we can list the bucket contents
            s3_path = f":s3:{bucket_name}"

            # Build rclone command with S3 backend flags
            command = [
                "rclone",
                "lsd",
                s3_path,
                "--max-depth",
                "1",
                "--verbose",  # Add verbose to get more error details
            ]

            # Add S3 configuration flags
            s3_flags = self._build_s3_flags(access_key_id, secret_access_key)
            command.extend(s3_flags)

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode("utf-8")
            stderr_text = stderr.decode("utf-8")

            if process.returncode == 0:
                # Test 2: Try to create and delete a test file to verify write permissions
                test_result = await self._test_s3_write_permissions(
                    access_key_id, secret_access_key, bucket_name
                )

                if test_result["status"] == "success":
                    return {
                        "status": "success",
                        "message": "Connection successful - bucket accessible and writable",
                        "output": stdout_text,
                        "details": {"read_test": "passed", "write_test": "passed"},
                    }
                else:
                    return {
                        "status": "warning",
                        "message": f"Bucket is readable but may have write permission issues: {test_result['message']}",
                        "output": stdout_text,
                        "details": {"read_test": "passed", "write_test": "failed"},
                    }
            else:
                # Analyze the error to provide better feedback
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
    ) -> Dict:
        """Test write permissions by creating and deleting a small test file"""
        try:
            import tempfile
            import os
            from datetime import datetime

            # Create a small test file
            test_content = f"borgitory-test-{datetime.now().isoformat()}"
            test_filename = (
                f"borgitory-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            )

            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name

            try:
                # Test upload
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
                    # Test cleanup - delete the test file
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
                # Clean up local temp file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

        except Exception as e:
            return {"status": "failed", "message": f"Write test failed: {str(e)}"}

    def parse_rclone_progress(self, line: str) -> Optional[Dict]:
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
        password: str = None,
        private_key: str = None,
    ) -> list:
        """Build SFTP configuration flags for rclone command"""
        flags = ["--sftp-host", host, "--sftp-user", username, "--sftp-port", str(port)]

        if password:
            # Obscure the password using rclone's method
            obscured_password = self._obscure_password(password)
            flags.extend(["--sftp-pass", obscured_password])
        elif private_key:
            # For private key auth, we need to write the key to a temporary file
            # and use --sftp-key-file
            import tempfile

            # Create temp file for private key
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
                # Fallback: just use the password as-is and let rclone handle it
                return password

        except Exception as e:
            logger.error(f"Failed to obscure password: {e}")
            # Fallback: just use the password as-is and let rclone handle it
            return password

    async def sync_repository_to_sftp(
        self,
        repository: Repository,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: str = None,
        private_key: str = None,
        path_prefix: str = "",
    ) -> AsyncGenerator[Dict, None]:
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
            # Extract key file path for cleanup later
            if "--sftp-key-file" in sftp_flags:
                key_file_idx = sftp_flags.index("--sftp-key-file")
                if key_file_idx + 1 < len(sftp_flags):
                    key_file_path = sftp_flags[key_file_idx + 1]

            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            yield {
                "type": "started",
                "command": " ".join(
                    [c for c in command if not c.startswith("--sftp-pass")]
                ),  # Hide password
                "pid": process.pid,
            }

            # Read stdout and stderr concurrently
            async def read_stream(stream, stream_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break

                    decoded_line = line.decode("utf-8").strip()
                    progress_data = self.parse_rclone_progress(decoded_line)

                    if progress_data:
                        yield {"type": "progress", **progress_data}
                    else:
                        yield {
                            "type": "log",
                            "stream": stream_type,
                            "message": decoded_line,
                        }

            # Stream both stdout and stderr
            async for item in self._merge_async_generators(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
            ):
                yield item

            # Wait for process to complete
            return_code = await process.wait()

            yield {
                "type": "completed",
                "return_code": return_code,
                "status": "success" if return_code == 0 else "failed",
            }

        except Exception as e:
            yield {"type": "error", "message": str(e)}
        finally:
            # Clean up temporary key file
            if key_file_path:
                try:
                    import os

                    os.unlink(key_file_path)
                except OSError:
                    pass

    async def test_sftp_connection(
        self,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: str = None,
        private_key: str = None,
    ) -> Dict:
        """Test SFTP connection by listing remote directory"""
        key_file_path = None
        try:
            # Build rclone command with SFTP backend flags
            sftp_path = f":sftp:{remote_path}"

            command = ["rclone", "lsd", sftp_path, "--max-depth", "1", "--verbose"]

            # Add SFTP configuration flags
            sftp_flags = self._build_sftp_flags(
                host, username, port, password, private_key
            )
            command.extend(sftp_flags)

            # Extract key file path for cleanup later
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
                # Test write permissions by trying to create a test directory
                test_result = await self._test_sftp_write_permissions(
                    host, username, remote_path, port, password, private_key
                )

                if test_result["status"] == "success":
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
                # Analyze the error to provide better feedback
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
            # Clean up temporary key file
            if key_file_path:
                try:
                    import os

                    os.unlink(key_file_path)
                except OSError:
                    pass

    async def _test_sftp_write_permissions(
        self,
        host: str,
        username: str,
        remote_path: str,
        port: int = 22,
        password: str = None,
        private_key: str = None,
    ) -> Dict:
        """Test write permissions by creating and deleting a small test file"""
        key_file_path = None
        temp_file_path = None

        try:
            import tempfile
            import os
            from datetime import datetime

            # Create a small test file
            test_content = f"borgitory-test-{datetime.now().isoformat()}"
            test_filename = (
                f"borgitory-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            )

            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name

            try:
                # Test upload
                sftp_path = f":sftp:{remote_path}/{test_filename}"

                upload_command = ["rclone", "copy", temp_file_path, sftp_path]

                sftp_flags = self._build_sftp_flags(
                    host, username, port, password, private_key
                )
                upload_command.extend(sftp_flags)

                # Extract key file path for cleanup later
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
                    # Test cleanup - delete the test file
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
                # Clean up local temp file
                if temp_file_path:
                    try:
                        os.unlink(temp_file_path)
                    except OSError:
                        pass

        except Exception as e:
            return {"status": "failed", "message": f"Write test failed: {str(e)}"}
        finally:
            # Clean up temporary key file
            if key_file_path:
                try:
                    import os

                    os.unlink(key_file_path)
                except OSError:
                    pass

    async def _merge_async_generators(self, *async_generators):
        """Merge multiple async generators into one"""
        tasks = []
        for gen in async_generators:

            async def wrapper(g):
                async for item in g:
                    yield item

            tasks.append(wrapper(gen))

        # This is a simplified merge - in production you'd want a more sophisticated approach
        for task in tasks:
            async for item in task:
                yield item

    def get_configured_remotes(self) -> list:
        """Get list of configured cloud backup configs from database"""
        # This method is no longer needed since we don't use config files
        # Cloud backup configurations are now stored in the database
        return []


# rclone_service = RcloneService()
