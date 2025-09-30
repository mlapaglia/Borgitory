"""
Tests for RcloneService - Behavioral tests focused on service functionality
"""

import pytest
from unittest.mock import Mock, AsyncMock
from borgitory.services.rclone_service import RcloneService
from borgitory.protocols.command_executor_protocol import (
    CommandExecutorProtocol,
    CommandResult,
)
from borgitory.models.database import Repository


@pytest.fixture
def mock_command_executor() -> Mock:
    """Create mock command executor."""
    mock = Mock(spec=CommandExecutorProtocol)
    mock.execute_command = AsyncMock()
    mock.create_subprocess = AsyncMock()
    return mock


@pytest.fixture
def rclone_service(mock_command_executor: Mock) -> RcloneService:
    """Create RcloneService with mock command executor."""
    return RcloneService(command_executor=mock_command_executor)


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock repository."""
    repo = Mock(spec=Repository)
    repo.path = "/test/repo/path"
    return repo


class TestRcloneServiceBasics:
    """Test basic RcloneService functionality."""

    def test_initialization(self, mock_command_executor: Mock) -> None:
        """Test RcloneService initializes correctly with command executor."""
        service = RcloneService(command_executor=mock_command_executor)
        assert service.command_executor is mock_command_executor

    def test_build_s3_flags(self, rclone_service: RcloneService) -> None:
        """Test S3 flags are built correctly."""
        flags = rclone_service._build_s3_flags(
            access_key_id="test_key",
            secret_access_key="test_secret",
            region="us-west-2",
            endpoint_url="https://s3.example.com",
            storage_class="GLACIER",
        )

        # Check that key flags are present (order may vary)
        assert "--s3-access-key-id" in flags
        assert "test_key" in flags
        assert "--s3-secret-access-key" in flags
        assert "test_secret" in flags
        assert "--s3-region" in flags
        assert "us-west-2" in flags
        assert "--s3-endpoint" in flags
        assert "https://s3.example.com" in flags
        assert "--s3-storage-class" in flags
        assert "GLACIER" in flags

    def test_build_sftp_flags_with_password(
        self, rclone_service: RcloneService
    ) -> None:
        """Test SFTP flags are built correctly with password."""
        flags = rclone_service._build_sftp_flags(
            host="sftp.example.com", username="testuser", port=2222, password="testpass"
        )

        assert "--sftp-host" in flags
        assert "sftp.example.com" in flags
        assert "--sftp-user" in flags
        assert "testuser" in flags
        assert "--sftp-port" in flags
        assert "2222" in flags
        assert "--sftp-pass" in flags

    def test_build_sftp_flags_with_private_key(
        self, rclone_service: RcloneService
    ) -> None:
        """Test SFTP flags are built correctly with private key."""
        flags = rclone_service._build_sftp_flags(
            host="sftp.example.com",
            username="testuser",
            private_key="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        )

        assert "--sftp-host" in flags
        assert "--sftp-user" in flags
        assert "--sftp-key-file" in flags


class TestRcloneServiceS3Operations:
    """Test S3-related operations."""

    @pytest.mark.asyncio
    async def test_test_s3_connection_success(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test successful S3 connection test."""
        # Mock successful command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["rclone", "lsd", ":s3:test-bucket"],
            return_code=0,
            stdout="2023/01/01 12:00:00     -1 test-folder",
            stderr="",
            success=True,
            execution_time=2.0,
        )

        result = await rclone_service.test_s3_connection(
            access_key_id="test_key",
            secret_access_key="test_secret",
            bucket_name="test-bucket",
        )

        assert result.get("status") == "success"
        assert "connection successful" in result.get("message", "").lower()
        # The method calls execute_command multiple times (read test + write test)
        assert mock_command_executor.execute_command.call_count >= 1

    @pytest.mark.asyncio
    async def test_test_s3_connection_bucket_not_found(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test S3 connection test with non-existent bucket."""
        # Mock failed command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["rclone", "lsd", ":s3:nonexistent-bucket"],
            return_code=1,
            stdout="",
            stderr="NoSuchBucket: The specified bucket does not exist",
            success=False,
            execution_time=1.0,
            error="NoSuchBucket: The specified bucket does not exist",
        )

        result = await rclone_service.test_s3_connection(
            access_key_id="test_key",
            secret_access_key="test_secret",
            bucket_name="nonexistent-bucket",
        )

        assert result.get("status") == "failed"
        assert "does not exist" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_sync_repository_to_s3_calls_executor(
        self,
        rclone_service: RcloneService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test that S3 sync calls the command executor with correct parameters."""
        # Mock subprocess for streaming
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess.return_value = mock_process

        # Collect results from the async generator
        results = []
        async for item in rclone_service.sync_repository_to_s3(
            repository=mock_repository,
            access_key_id="test_key",
            secret_access_key="test_secret",
            bucket_name="test-bucket",
        ):
            results.append(item)
            break  # Just get the first item to test the call

        # Verify the command executor was called
        mock_command_executor.create_subprocess.assert_called_once()
        call_args = mock_command_executor.create_subprocess.call_args

        # Verify the command contains expected elements
        command = call_args[1]["command"]
        assert "rclone" in command
        assert "sync" in command
        assert mock_repository.path in command
        assert ":s3:test-bucket" in command

        # Verify we got a started event
        assert len(results) > 0
        assert results[0]["type"] == "started"


class TestRcloneServiceSFTPOperations:
    """Test SFTP-related operations."""

    @pytest.mark.asyncio
    async def test_test_sftp_connection_success(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test successful SFTP connection test."""
        # Mock successful command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["rclone", "lsd", ":sftp:/remote/path"],
            return_code=0,
            stdout="2023/01/01 12:00:00     -1 test-folder",
            stderr="",
            success=True,
            execution_time=2.0,
        )

        result = await rclone_service.test_sftp_connection(
            host="sftp.example.com",
            username="testuser",
            remote_path="/remote/path",
            password="testpass",
        )

        assert result.get("status") == "success"
        assert "connection successful" in result.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_test_sftp_connection_auth_failed(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test SFTP connection test with authentication failure."""
        # Mock failed command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["rclone", "lsd", ":sftp:/remote/path"],
            return_code=1,
            stdout="",
            stderr="ssh: handshake failed: ssh: unable to authenticate",
            success=False,
            execution_time=5.0,
            error="ssh: handshake failed: ssh: unable to authenticate",
        )

        result = await rclone_service.test_sftp_connection(
            host="sftp.example.com",
            username="testuser",
            remote_path="/remote/path",
            password="wrongpass",
        )

        assert result.get("status") == "failed"
        message = result.get("message", "").lower()
        assert "ssh" in message or "authentication" in message


class TestRcloneServiceSMBOperations:
    """Test SMB-related operations."""

    @pytest.mark.asyncio
    async def test_test_smb_connection_success(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test successful SMB connection test."""
        # Mock successful command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["rclone", "lsd", ":smb:share"],
            return_code=0,
            stdout="2023/01/01 12:00:00     -1 test-folder",
            stderr="",
            success=True,
            execution_time=2.0,
        )

        result = await rclone_service.test_smb_connection(
            host="smb.example.com",
            user="testuser",
            share_name="share",
            password="testpass",
        )

        assert result.get("status") == "success"
        assert "connected" in result.get("message", "").lower()

    def test_build_smb_flags(self, rclone_service: RcloneService) -> None:
        """Test SMB flags are built correctly."""
        flags = rclone_service._build_smb_flags(
            host="smb.example.com",
            user="testuser",
            password="testpass",
            port=445,
            domain="WORKGROUP",
        )

        assert "--smb-host" in flags
        assert "smb.example.com" in flags
        assert "--smb-user" in flags
        assert "testuser" in flags
        assert "--smb-port" in flags
        assert "445" in flags
        assert "--smb-domain" in flags
        assert "WORKGROUP" in flags


class TestRcloneServiceGenericDispatchers:
    """Test generic dispatcher methods."""

    def test_has_generic_dispatcher_methods(
        self, rclone_service: RcloneService
    ) -> None:
        """Test that RcloneService has the required generic dispatcher methods."""
        # Verify the generic dispatcher methods exist
        assert hasattr(rclone_service, "sync_repository_to_provider")
        assert callable(getattr(rclone_service, "sync_repository_to_provider"))
        assert hasattr(rclone_service, "test_provider_connection")
        assert callable(getattr(rclone_service, "test_provider_connection"))

    @pytest.mark.asyncio
    async def test_test_provider_connection_sftp(
        self, rclone_service: RcloneService
    ) -> None:
        """Test generic connection test dispatcher for SFTP."""
        # Mock the specific SFTP test method using patch
        from unittest.mock import patch

        with patch.object(
            rclone_service, "test_sftp_connection", new_callable=AsyncMock
        ) as mock_sftp:
            mock_sftp.return_value = {"status": "success"}

            result = await rclone_service.test_provider_connection(
                "sftp",
                host="sftp.example.com",
                username="testuser",
                remote_path="/remote/path",
            )

            # Verify the SFTP-specific method was called and result returned
            mock_sftp.assert_called_once()
            assert result.get("status") == "success"

    @pytest.mark.asyncio
    async def test_sync_repository_to_provider_unsupported(
        self, rclone_service: RcloneService, mock_repository: Mock
    ) -> None:
        """Test generic sync dispatcher with unsupported provider."""
        with pytest.raises(ValueError, match="no rclone mapping configured"):
            async for _ in rclone_service.sync_repository_to_provider(
                "unsupported", mock_repository
            ):
                pass

    @pytest.mark.asyncio
    async def test_test_provider_connection_unsupported(
        self, rclone_service: RcloneService
    ) -> None:
        """Test generic connection test dispatcher with unsupported provider."""
        with pytest.raises(ValueError, match="no rclone mapping configured"):
            await rclone_service.test_provider_connection("unsupported")


class TestRcloneServiceErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_connection_test_exception_handling(
        self, rclone_service: RcloneService, mock_command_executor: Mock
    ) -> None:
        """Test that connection tests handle exceptions gracefully."""
        # Mock command executor to raise an exception
        mock_command_executor.execute_command.side_effect = Exception("Network error")

        result = await rclone_service.test_s3_connection(
            access_key_id="test_key",
            secret_access_key="test_secret",
            bucket_name="test-bucket",
        )

        assert result.get("status") == "error"
        assert "exception" in result.get("message", "").lower()

    @pytest.mark.asyncio
    async def test_sync_operation_exception_handling(
        self,
        rclone_service: RcloneService,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test that sync operations handle exceptions gracefully."""
        # Mock command executor to raise an exception
        mock_command_executor.create_subprocess.side_effect = Exception("Process error")

        results = []
        async for item in rclone_service.sync_repository_to_s3(
            repository=mock_repository,
            access_key_id="test_key",
            secret_access_key="test_secret",
            bucket_name="test-bucket",
        ):
            results.append(item)

        # Should get an error event
        assert len(results) > 0
        assert any(item["type"] == "error" for item in results)
