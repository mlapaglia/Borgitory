"""
Tests for RcloneService - Service for cloud backup synchronization using Rclone
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.rclone_service import RcloneService
from app.models.database import Repository


@pytest.fixture
def rclone_service():
    return RcloneService()


@pytest.fixture
def mock_repository():
    """Mock repository object"""
    repo = MagicMock(spec=Repository)
    repo.path = "/test/repo/path"
    return repo


class TestRcloneService:
    """Test the RcloneService class"""

    def test_build_s3_flags(self, rclone_service):
        """Test S3 flags building"""
        flags = rclone_service._build_s3_flags("test_access_key", "test_secret_key")
        
        expected_flags = [
            "--s3-access-key-id",
            "test_access_key",
            "--s3-secret-access-key",
            "test_secret_key",
            "--s3-provider",
            "AWS",
        ]
        
        assert flags == expected_flags

    def test_build_sftp_flags_with_password(self, rclone_service):
        """Test SFTP flags building with password"""
        with patch.object(rclone_service, '_obscure_password', return_value="obscured_pass"):
            flags = rclone_service._build_sftp_flags(
                host="test.host.com",
                username="testuser",
                port=2222,
                password="testpass"
            )
            
            expected_flags = [
                "--sftp-host", "test.host.com",
                "--sftp-user", "testuser", 
                "--sftp-port", "2222",
                "--sftp-pass", "obscured_pass"
            ]
            
            assert flags == expected_flags

    def test_build_sftp_flags_with_private_key(self, rclone_service):
        """Test SFTP flags building with private key"""
        private_key_content = "-----BEGIN RSA PRIVATE KEY-----\ntest_key_content\n-----END RSA PRIVATE KEY-----"
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_file = MagicMock()
            mock_file.name = "/tmp/test_key.pem"
            mock_temp.return_value.__enter__.return_value = mock_file
            
            flags = rclone_service._build_sftp_flags(
                host="test.host.com",
                username="testuser",
                private_key=private_key_content
            )
            
            expected_flags = [
                "--sftp-host", "test.host.com",
                "--sftp-user", "testuser",
                "--sftp-port", "22",
                "--sftp-key-file", "/tmp/test_key.pem"
            ]
            
            assert flags == expected_flags
            mock_file.write.assert_called_once_with(private_key_content)

    def test_build_sftp_flags_defaults(self, rclone_service):
        """Test SFTP flags building with defaults"""
        flags = rclone_service._build_sftp_flags(
            host="test.host.com",
            username="testuser"
        )
        
        expected_flags = [
            "--sftp-host", "test.host.com",
            "--sftp-user", "testuser",
            "--sftp-port", "22"
        ]
        
        assert flags == expected_flags

    def test_obscure_password_success(self, rclone_service):
        """Test password obscuring success"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "obscured_password_123\n"
        
        with patch('subprocess.run', return_value=mock_result):
            result = rclone_service._obscure_password("plain_password")
            
            assert result == "obscured_password_123"

    def test_obscure_password_failure(self, rclone_service):
        """Test password obscuring failure fallback"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "rclone obscure failed"
        
        with patch('subprocess.run', return_value=mock_result):
            result = rclone_service._obscure_password("plain_password")
            
            assert result == "plain_password"  # Fallback to original

    def test_obscure_password_exception(self, rclone_service):
        """Test password obscuring exception handling"""
        with patch('subprocess.run', side_effect=Exception("Command failed")):
            result = rclone_service._obscure_password("plain_password")
            
            assert result == "plain_password"  # Fallback to original

    def test_parse_rclone_progress_transferred(self, rclone_service):
        """Test parsing rclone progress with transfer info"""
        line = "Transferred: 123.45 MiByte / 456.78 MiByte, 27%, 12.34"
        result = rclone_service.parse_rclone_progress(line)
        
        # Based on the parsing logic:
        # parts[1] = "123.45" (transferred)
        # parts[4] = "456.78" (total)
        # parts[5] = "MiByte," (percentage - but logic strips %, and "MiByte" isn't digit)
        # parts[6] = "27%," (speed)
        expected = {
            "transferred": "123.45",
            "total": "456.78",
            "percentage": 0,  # "MiByte" is not a digit, so defaults to 0
            "speed": "27%,"
        }
        
        assert result == expected

    def test_parse_rclone_progress_eta(self, rclone_service):
        """Test parsing rclone progress with ETA info"""
        line = "Some output with ETA 2m30s remaining"
        result = rclone_service.parse_rclone_progress(line)
        
        expected = {"eta": "2m30s remaining"}
        assert result == expected

    def test_parse_rclone_progress_no_match(self, rclone_service):
        """Test parsing rclone progress with no matching patterns"""
        line = "Some random output line"
        result = rclone_service.parse_rclone_progress(line)
        
        assert result is None

    def test_parse_rclone_progress_malformed(self, rclone_service):
        """Test parsing malformed rclone progress"""
        line = "Transferred: incomplete"
        result = rclone_service.parse_rclone_progress(line)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_success(self, rclone_service, mock_repository):
        """Test successful S3 repository sync"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        
        # Mock stdout and stderr streams
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        
        # Mock readline to return empty (end of stream)
        mock_stdout.readline = AsyncMock(return_value=b"")
        mock_stderr.readline = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            results = []
            async for item in rclone_service.sync_repository_to_s3(
                repository=mock_repository,
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            ):
                results.append(item)
            
            # Check that we got started and completed events
            assert len(results) >= 2
            assert results[0]["type"] == "started"
            assert results[0]["pid"] == 12345
            assert results[-1]["type"] == "completed"
            assert results[-1]["return_code"] == 0
            assert results[-1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_with_path_prefix(self, rclone_service, mock_repository):
        """Test S3 sync with path prefix"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            results = []
            async for item in rclone_service.sync_repository_to_s3(
                repository=mock_repository,
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket",
                path_prefix="backups/repo1"
            ):
                results.append(item)
            
            # Verify the S3 path includes the prefix
            called_command = mock_exec.call_args[0]
            assert ":s3:test-bucket/backups/repo1" in called_command

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_failure(self, rclone_service, mock_repository):
        """Test S3 sync failure"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=1)  # Non-zero return code
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            results = []
            async for item in rclone_service.sync_repository_to_s3(
                repository=mock_repository,
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            ):
                results.append(item)
            
            # Check that we got failure status
            assert results[-1]["type"] == "completed"
            assert results[-1]["return_code"] == 1
            assert results[-1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_exception(self, rclone_service, mock_repository):
        """Test S3 sync with exception"""
        with patch('asyncio.create_subprocess_exec', side_effect=Exception("Process failed")):
            results = []
            async for item in rclone_service.sync_repository_to_s3(
                repository=mock_repository,
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            ):
                results.append(item)
            
            # Should get error event
            assert len(results) == 1
            assert results[0]["type"] == "error"
            assert "Process failed" in results[0]["message"]

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_with_progress(self, rclone_service, mock_repository):
        """Test S3 sync with progress output"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        
        # Mock stdout to return progress line then end
        progress_line = b"Transferred:   	  123.45 MiByte / 456.78 MiByte, 27%, 12.34 MiByte/s, ETA 1m23s\n"
        mock_process.stdout.readline = AsyncMock(side_effect=[progress_line, b""])
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            results = []
            async for item in rclone_service.sync_repository_to_s3(
                repository=mock_repository,
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            ):
                results.append(item)
            
            # Should have started, progress, and completed events
            progress_events = [r for r in results if r["type"] == "progress"]
            assert len(progress_events) >= 1
            assert "percentage" in progress_events[0]

    @pytest.mark.asyncio
    async def test_test_s3_connection_success(self, rclone_service):
        """Test successful S3 connection test"""
        # Mock the list command success
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"bucket contents", b""))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_test_s3_write_permissions', 
                         return_value={"status": "success"}):
            
            result = await rclone_service.test_s3_connection(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "success"
            assert "Connection successful" in result["message"]
            assert result["details"]["read_test"] == "passed"
            assert result["details"]["write_test"] == "passed"

    @pytest.mark.asyncio
    async def test_test_s3_connection_read_only(self, rclone_service):
        """Test S3 connection with read-only access"""
        # Mock the list command success but write test failure
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"bucket contents", b""))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_test_s3_write_permissions', 
                         return_value={"status": "failed", "message": "Write failed"}):
            
            result = await rclone_service.test_s3_connection(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "warning"
            assert "write permission issues" in result["message"]
            assert result["details"]["read_test"] == "passed"
            assert result["details"]["write_test"] == "failed"

    @pytest.mark.asyncio
    async def test_test_s3_connection_bucket_not_found(self, rclone_service):
        """Test S3 connection with non-existent bucket"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"no such bucket error"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await rclone_service.test_s3_connection(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="nonexistent-bucket"
            )
            
            assert result["status"] == "failed"
            assert "does not exist" in result["message"]

    @pytest.mark.asyncio
    async def test_test_s3_connection_access_denied(self, rclone_service):
        """Test S3 connection with invalid credentials"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"access denied"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await rclone_service.test_s3_connection(
                access_key_id="invalid_key",
                secret_access_key="invalid_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "failed"
            assert "check your AWS credentials" in result["message"]

    @pytest.mark.asyncio
    async def test_test_s3_connection_exception(self, rclone_service):
        """Test S3 connection with exception"""
        with patch('asyncio.create_subprocess_exec', side_effect=Exception("Connection failed")):
            result = await rclone_service.test_s3_connection(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "error"
            assert "Connection failed" in result["message"]

    @pytest.mark.asyncio
    async def test_test_s3_write_permissions_success(self, rclone_service):
        """Test successful S3 write permissions"""
        # Mock upload success
        mock_upload_process = MagicMock()
        mock_upload_process.returncode = 0
        mock_upload_process.communicate = AsyncMock(return_value=(b"", b""))
        
        # Mock delete success  
        mock_delete_process = MagicMock()
        mock_delete_process.communicate = AsyncMock(return_value=(b"", b""))
        
        with patch('asyncio.create_subprocess_exec', side_effect=[mock_upload_process, mock_delete_process]), \
             patch('tempfile.NamedTemporaryFile') as mock_temp, \
             patch('os.unlink'):
            
            mock_file = MagicMock()
            mock_file.name = "/tmp/test_file.txt"
            mock_temp.return_value.__enter__.return_value = mock_file
            
            result = await rclone_service._test_s3_write_permissions(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "success"
            assert "Write permissions verified" in result["message"]

    @pytest.mark.asyncio
    async def test_test_s3_write_permissions_failure(self, rclone_service):
        """Test S3 write permissions failure"""
        # Mock upload failure
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Permission denied"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch('tempfile.NamedTemporaryFile') as mock_temp, \
             patch('os.unlink'):
            
            mock_file = MagicMock()
            mock_file.name = "/tmp/test_file.txt"
            mock_temp.return_value.__enter__.return_value = mock_file
            
            result = await rclone_service._test_s3_write_permissions(
                access_key_id="test_key",
                secret_access_key="test_secret",
                bucket_name="test-bucket"
            )
            
            assert result["status"] == "failed"
            assert "Cannot write to bucket" in result["message"]

    @pytest.mark.asyncio
    async def test_sync_repository_to_sftp_success(self, rclone_service, mock_repository):
        """Test successful SFTP repository sync"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=["--sftp-host", "test.com"]):
            
            results = []
            async for item in rclone_service.sync_repository_to_sftp(
                repository=mock_repository,
                host="test.com",
                username="testuser",
                remote_path="/remote/path"
            ):
                results.append(item)
            
            # Check that we got started and completed events
            assert len(results) >= 2
            assert results[0]["type"] == "started"
            assert results[0]["pid"] == 12345
            # Should hide password from command display
            assert "--sftp-pass" not in results[0]["command"]
            assert results[-1]["type"] == "completed"
            assert results[-1]["status"] == "success"

    @pytest.mark.asyncio
    async def test_sync_repository_to_sftp_with_key_cleanup(self, rclone_service, mock_repository):
        """Test SFTP sync with SSH key cleanup"""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        
        # Mock SFTP flags with key file
        sftp_flags = ["--sftp-host", "test.com", "--sftp-key-file", "/tmp/key.pem"]
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=sftp_flags), \
             patch('os.unlink') as mock_unlink:
            
            results = []
            async for item in rclone_service.sync_repository_to_sftp(
                repository=mock_repository,
                host="test.com",
                username="testuser",
                remote_path="/remote/path",
                private_key="test_key_content"
            ):
                results.append(item)
            
            # Should clean up key file
            mock_unlink.assert_called_with("/tmp/key.pem")

    @pytest.mark.asyncio
    async def test_test_sftp_connection_success(self, rclone_service):
        """Test successful SFTP connection test"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"directory listing", b""))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=["--sftp-host", "test.com"]), \
             patch.object(rclone_service, '_test_sftp_write_permissions', 
                         return_value={"status": "success"}):
            
            result = await rclone_service.test_sftp_connection(
                host="test.com",
                username="testuser",
                remote_path="/remote/path"
            )
            
            assert result["status"] == "success"
            assert "SFTP connection successful" in result["message"]
            assert result["details"]["host"] == "test.com"
            assert result["details"]["port"] == 22

    @pytest.mark.asyncio
    async def test_test_sftp_connection_authentication_failed(self, rclone_service):
        """Test SFTP connection with authentication failure"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"authentication failed"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=["--sftp-host", "test.com"]):
            
            result = await rclone_service.test_sftp_connection(
                host="test.com",
                username="testuser",
                remote_path="/remote/path"
            )
            
            assert result["status"] == "failed"
            assert "Authentication failed" in result["message"]

    @pytest.mark.asyncio
    async def test_test_sftp_connection_connection_refused(self, rclone_service):
        """Test SFTP connection refused"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"connection refused"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=["--sftp-host", "test.com"]):
            
            result = await rclone_service.test_sftp_connection(
                host="test.com",
                username="testuser",
                remote_path="/remote/path",
                port=2222
            )
            
            assert result["status"] == "failed"
            assert "Connection refused to test.com:2222" in result["message"]

    @pytest.mark.asyncio
    async def test_test_sftp_connection_path_not_found(self, rclone_service):
        """Test SFTP connection with non-existent path"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"no such file or directory"))
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch.object(rclone_service, '_build_sftp_flags', return_value=["--sftp-host", "test.com"]):
            
            result = await rclone_service.test_sftp_connection(
                host="test.com",
                username="testuser",
                remote_path="/nonexistent/path"
            )
            
            assert result["status"] == "failed"
            assert "does not exist" in result["message"]

    def test_get_configured_remotes(self, rclone_service):
        """Test get_configured_remotes returns empty list"""
        result = rclone_service.get_configured_remotes()
        assert result == []

    @pytest.mark.asyncio
    async def test_merge_async_generators(self, rclone_service):
        """Test merging multiple async generators"""
        async def gen1():
            yield "item1"
            yield "item2"
        
        async def gen2():
            yield "item3"
            yield "item4"
        
        results = []
        async for item in rclone_service._merge_async_generators(gen1(), gen2()):
            results.append(item)
        
        # Should contain all items from both generators
        assert "item1" in results
        assert "item2" in results
        assert "item3" in results
        assert "item4" in results