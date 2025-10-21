"""
Tests for cloud storage implementations.

These tests focus on the storage layer in isolation, with clean mocking
and simple assertions. Each test has a single responsibility.
"""

import pytest
from unittest.mock import AsyncMock
from pydantic import ValidationError
from borgitory.services.cloud_providers.storage import (
    S3Storage,
    SFTPStorage,
    S3StorageConfig,
    SFTPStorageConfig,
)
from borgitory.services.cloud_providers.types import (
    SyncEvent,
    SyncEventType,
    ConnectionInfo,
)
from borgitory.protocols.command_executor_protocol import (
    CommandExecutorProtocol,
    CommandResult,
)
from borgitory.protocols.file_protocols import FileServiceProtocol


class TestS3StorageConfig:
    """Test S3 storage configuration validation"""

    def test_valid_s3_config(self) -> None:
        """Test creating valid S3 config"""
        config = S3StorageConfig(
            bucket_name="my-backup-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-west-2",
            storage_class="GLACIER",
        )

        assert config.bucket_name == "my-backup-bucket"
        assert config.access_key == "AKIAIOSFODNN7EXAMPLE"
        assert config.secret_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert config.region == "us-west-2"
        assert config.storage_class == "GLACIER"
        assert config.endpoint_url is None

    def test_s3_config_with_defaults(self) -> None:
        """Test S3 config with default values"""
        config = S3StorageConfig(
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )

        assert config.region == "us-east-1"  # Default
        assert config.storage_class == "STANDARD"  # Default
        assert config.endpoint_url is None

    def test_s3_config_with_custom_endpoint(self) -> None:
        """Test S3 config with custom endpoint (MinIO, etc.)"""
        config = S3StorageConfig(
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            endpoint_url="https://minio.example.com:9000",
        )

        assert config.endpoint_url == "https://minio.example.com:9000"

    def test_bucket_name_normalization(self) -> None:
        """Test that bucket names are normalized to lowercase"""
        config = S3StorageConfig(
            bucket_name="MY-UPPERCASE-BUCKET",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )

        assert config.bucket_name == "my-uppercase-bucket"

    def test_invalid_bucket_name_too_short(self) -> None:
        """Test validation of bucket name too short"""
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="ab",  # Too short
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )

        assert "at least 3 characters" in str(exc_info.value)

    def test_invalid_bucket_name_too_long(self) -> None:
        """Test validation of bucket name too long"""
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="a" * 64,  # Too long
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )

        assert "at most 63 characters" in str(exc_info.value)

    def test_invalid_storage_class(self) -> None:
        """Test validation of invalid storage class"""
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                storage_class="INVALID_CLASS",
            )

        assert "is not supported by" in str(exc_info.value)

    def test_storage_class_normalization(self) -> None:
        """Test that storage class is normalized to uppercase"""
        config = S3StorageConfig(
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            storage_class="glacier",  # lowercase
        )

        assert config.storage_class == "GLACIER"

    def test_all_valid_storage_classes(self) -> None:
        """Test all valid storage classes"""
        valid_classes = [
            "STANDARD",
            "REDUCED_REDUNDANCY",
            "STANDARD_IA",
            "ONEZONE_IA",
            "INTELLIGENT_TIERING",
            "GLACIER",
            "DEEP_ARCHIVE",
        ]

        for storage_class in valid_classes:
            config = S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                storage_class=storage_class,
            )
            assert config.storage_class == storage_class

    def test_empty_access_key(self) -> None:
        """Test validation of empty access key"""
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="",  # Empty
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )

        assert "String should have at least 16 char" in str(exc_info.value)

    def test_empty_secret_key(self) -> None:
        """Test validation of empty secret key"""
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="",  # Empty
            )

        assert "String should have at least 16 char" in str(exc_info.value)

    def test_invalid_access_key_format(self) -> None:
        """Test validation of access key format"""
        # Test key not starting with AKIA
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="NOTAKIA123456789",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        assert "must start with 'AKIA'" in str(exc_info.value)

        # Test key with wrong length (too short)
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIA123",  # Too short
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        assert "String should have at least 16 characters" in str(exc_info.value)

        # Test key with non-alphanumeric characters (exactly 20 chars)
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIA123456789012345-",  # Contains hyphen, exactly 20 chars
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        assert "must contain only alphanumeric characters" in str(exc_info.value)

        # Test key with valid length but wrong prefix
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="NOTAKIA123456789012",  # Exactly 20 chars but wrong prefix
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        assert "must start with 'AKIA'" in str(exc_info.value)

    def test_invalid_secret_key_format(self) -> None:
        """Test validation of secret key format"""
        # Test key with wrong length (too short)
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLE",  # Too short
            )
        assert "must be exactly 40 characters long" in str(exc_info.value)

        # Test key with invalid characters (exactly 40 chars)
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKE@",  # Contains @, exactly 40 chars
            )
        assert "contains invalid characters" in str(exc_info.value)

        # Test key with wrong length (too long)
        with pytest.raises(ValidationError) as exc_info:
            S3StorageConfig(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEYX",  # 41 chars
            )
        assert "must be exactly 40 characters long" in str(exc_info.value)


class TestSFTPStorageConfig:
    """Test SFTP storage configuration validation"""

    def test_valid_sftp_config_with_password(self) -> None:
        """Test creating valid SFTP config with password"""
        config = SFTPStorageConfig(
            host="backup.example.com",
            username="backup_user",
            password="secure_password",
            remote_path="/backups/borg",
            port=2222,
        )

        assert config.host == "backup.example.com"
        assert config.username == "backup_user"
        assert config.password == "secure_password"
        assert config.private_key is None
        assert config.remote_path == "/backups/borg"
        assert config.port == 2222
        assert config.host_key_checking is True

    def test_valid_sftp_config_with_private_key(self) -> None:
        """Test creating valid SFTP config with private key"""
        private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC..."
        config = SFTPStorageConfig(
            host="backup.example.com",
            username="backup_user",
            private_key=private_key,
            remote_path="/backups",
        )

        assert config.host == "backup.example.com"
        assert config.username == "backup_user"
        assert config.password is None
        assert config.private_key == private_key
        assert config.remote_path == "/backups"
        assert config.port == 22  # Default

    def test_sftp_config_with_both_auth_methods(self) -> None:
        """Test SFTP config with both password and private key"""
        config = SFTPStorageConfig(
            host="backup.example.com",
            username="backup_user",
            password="password",
            private_key="private_key_content",
            remote_path="/backups",
        )

        # Both should be preserved
        assert config.password == "password"
        assert config.private_key == "private_key_content"

    def test_remote_path_normalization(self) -> None:
        """Test remote path normalization"""
        test_cases = [
            ("backups", "/backups"),
            ("/backups", "/backups"),
            ("backups/", "/backups"),
            ("/backups/", "/backups"),
            ("backups/borg/", "/backups/borg"),
        ]

        for input_path, expected in test_cases:
            config = SFTPStorageConfig(
                host="example.com",
                username="user",
                password="pass",
                remote_path=input_path,
            )
            assert config.remote_path == expected

    def test_missing_authentication(self) -> None:
        """Test that missing authentication fails validation"""
        with pytest.raises(ValidationError) as exc_info:
            SFTPStorageConfig(
                host="backup.example.com",
                username="backup_user",
                # No password or private_key
                remote_path="/backups",
            )

        assert "Either password or private_key must be provided" in str(exc_info.value)

    def test_invalid_port_range(self) -> None:
        """Test port validation"""
        # Port too low
        with pytest.raises(ValidationError):
            SFTPStorageConfig(
                host="example.com",
                username="user",
                password="pass",
                remote_path="/backups",
                port=0,
            )

        # Port too high
        with pytest.raises(ValidationError):
            SFTPStorageConfig(
                host="example.com",
                username="user",
                password="pass",
                remote_path="/backups",
                port=65536,
            )

    def test_valid_port_range(self) -> None:
        """Test valid port values"""
        valid_ports = [1, 22, 443, 2222, 65535]

        for port in valid_ports:
            config = SFTPStorageConfig(
                host="example.com",
                username="user",
                password="pass",
                remote_path="/backups",
                port=port,
            )
            assert config.port == port

    def test_empty_host(self) -> None:
        """Test validation of empty host"""
        with pytest.raises(ValidationError):
            SFTPStorageConfig(
                host="",  # Empty
                username="user",
                password="pass",
                remote_path="/backups",
            )

    def test_empty_username(self) -> None:
        """Test validation of empty username"""
        with pytest.raises(ValidationError):
            SFTPStorageConfig(
                host="example.com",
                username="",  # Empty
                password="pass",
                remote_path="/backups",
            )

    def test_empty_remote_path(self) -> None:
        """Test validation of empty remote path"""
        with pytest.raises(ValidationError):
            SFTPStorageConfig(
                host="example.com",
                username="user",
                password="pass",
                remote_path="",  # Empty
            )


class TestS3Storage:
    """Test S3Storage implementation"""

    @pytest.fixture
    def s3_config(self) -> S3StorageConfig:
        """Valid S3 configuration"""
        return S3StorageConfig(
            bucket_name="test-bucket",
            access_key="AKIATESTKEY123456789",  # Exactly 20 chars
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-west-2",
        )

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        """Mock command executor"""
        return AsyncMock(spec=CommandExecutorProtocol)

    @pytest.fixture
    def mock_file_service(self) -> AsyncMock:
        """Mock file service"""
        return AsyncMock(spec=FileServiceProtocol)

    @pytest.fixture
    def s3_storage(
        self,
        s3_config: S3StorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> S3Storage:
        """S3Storage instance with mocked dependencies"""
        return S3Storage(s3_config, mock_command_executor, mock_file_service)

    def test_initialization(
        self,
        s3_config: S3StorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> None:
        """Test S3Storage initialization"""
        storage = S3Storage(s3_config, mock_command_executor, mock_file_service)

        assert storage._config is s3_config
        assert storage._command_executor is mock_command_executor
        assert storage._file_service is mock_file_service

    def test_get_connection_info(self, s3_storage: S3Storage) -> None:
        """Test getting connection info"""
        info = s3_storage.get_connection_info()

        assert isinstance(info, ConnectionInfo)
        assert info.provider == "s3"
        assert info.details["bucket"] == "test-bucket"
        assert info.details["region"] == "us-west-2"
        assert info.details["storage_class"] == "STANDARD"

        # Access key should be masked
        access_key_display = info.details["access_key"]
        assert isinstance(access_key_display, str)
        assert access_key_display.startswith("AKIA")
        assert "***" in access_key_display
        assert len(access_key_display) <= len(
            "AKIATESTKEY123456789"
        )  # Could be same length if masking pattern changes

    def test_get_connection_info_short_access_key(
        self, mock_command_executor: AsyncMock, mock_file_service: AsyncMock
    ) -> None:
        """Test connection info with short access key that still meets validation"""
        config = S3StorageConfig(
            bucket_name="test-bucket",
            access_key="AKIASHORTKEY12345678",  # Still 20 chars but "short" for masking
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        )
        storage = S3Storage(config, mock_command_executor, mock_file_service)

        info = storage.get_connection_info()
        # Should still mask the key
        assert isinstance(info.details["access_key"], str)
        assert "***" in info.details["access_key"]

    def test_get_sensitive_fields(self, s3_storage: S3Storage) -> None:
        """Test getting sensitive field names"""
        fields = s3_storage.get_sensitive_fields()

        assert fields == ["access_key", "secret_key"]
        assert isinstance(fields, list)

    async def test_upload_repository_success(
        self, s3_storage: S3Storage, mock_command_executor: AsyncMock
    ) -> None:
        """Test successful repository upload"""

        # Mock the subprocess that sync_repository_to_s3 creates
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)  # Success

        # Create a callable that returns items from a list, then empty bytes
        stdout_responses = [
            b"Transferred: 50% complete\n",
            b"Transferred: 90% complete\n",
        ]
        stdout_iter = iter(stdout_responses)

        async def mock_stdout_readline() -> bytes:
            try:
                return next(stdout_iter)
            except StopIteration:
                return b""

        mock_process.stdout.readline = mock_stdout_readline
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess = AsyncMock(return_value=mock_process)

        # Capture progress events
        events = []

        def progress_callback(event: SyncEvent) -> None:
            events.append(event)

        # Execute upload
        await s3_storage.upload_repository(
            repository_path="/test/repo",
            remote_path="backups/2023",
            progress_callback=progress_callback,
        )

        # Verify events - START + COMPLETED at minimum
        assert len(events) >= 2
        assert events[0].type == SyncEventType.STARTED
        assert "upload to bucket test-bucket" in events[0].message
        assert events[-1].type == SyncEventType.COMPLETED
        assert "completed successfully" in events[-1].message

    async def test_upload_repository_without_callback(
        self, s3_storage: S3Storage, mock_command_executor: AsyncMock
    ) -> None:
        """Test upload without progress callback"""

        # Mock successful subprocess
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess = AsyncMock(return_value=mock_process)

        # Should not raise exception
        await s3_storage.upload_repository("/test/repo", "backups/")

    async def test_upload_repository_error(
        self, s3_storage: S3Storage, mock_command_executor: AsyncMock
    ) -> None:
        """Test upload with error"""

        # Mock subprocess that fails (return code 1)
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=1)  # Failed
        mock_process.stdout.readline = AsyncMock(return_value=b"")

        # Return error once, then empty bytes
        stderr_responses = [b"Error: Network timeout\n"]
        stderr_iter = iter(stderr_responses)

        async def mock_stderr_readline() -> bytes:
            try:
                return next(stderr_iter)
            except StopIteration:
                return b""

        mock_process.stderr.readline = mock_stderr_readline

        mock_command_executor.create_subprocess = AsyncMock(return_value=mock_process)

        events = []

        def progress_callback(event: SyncEvent) -> None:
            events.append(event)

        # Should raise exception
        with pytest.raises(Exception):
            await s3_storage.upload_repository(
                "/test/repo", "backups/", progress_callback
            )

        # Should have START and ERROR events
        assert len(events) >= 2
        assert events[0].type == SyncEventType.STARTED
        assert any(e.type == SyncEventType.ERROR for e in events)

    async def test_test_connection_success(
        self,
        s3_storage: S3Storage,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> None:
        """Test successful connection test"""
        # Mock successful lsd command and write test
        mock_command_executor.execute_command = AsyncMock(
            return_value=CommandResult(
                command=["rclone", "lsd", ":s3:test-bucket"],
                return_code=0,
                stdout="2023/01/01 12:00:00     -1 test-folder",
                stderr="",
                success=True,
                execution_time=1.0,
            )
        )

        # Mock successful write test - create a proper async context manager
        from unittest.mock import MagicMock

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value="/tmp/test")
        async_cm.__aexit__ = AsyncMock(return_value=None)
        mock_file_service.create_temp_file = MagicMock(return_value=async_cm)

        result = await s3_storage.test_connection()

        assert result is True

    async def test_test_connection_failure(
        self, s3_storage: S3Storage, mock_command_executor: AsyncMock
    ) -> None:
        """Test failed connection test"""
        mock_command_executor.execute_command = AsyncMock(
            return_value=CommandResult(
                command=["rclone", "lsd", ":s3:test-bucket"],
                return_code=1,
                stdout="",
                stderr="NoSuchBucket: The specified bucket does not exist",
                success=False,
                execution_time=1.0,
                error="NoSuchBucket: The specified bucket does not exist",
            )
        )

        result = await s3_storage.test_connection()
        assert result is False

    async def test_test_connection_exception(
        self, s3_storage: S3Storage, mock_command_executor: AsyncMock
    ) -> None:
        """Test connection test with exception"""
        mock_command_executor.execute_command = AsyncMock(
            side_effect=Exception("Network error")
        )

        result = await s3_storage.test_connection()
        assert result is False


class TestSFTPStorage:
    """Test SFTPStorage implementation"""

    @pytest.fixture
    def sftp_config(self) -> SFTPStorageConfig:
        """Valid SFTP configuration"""
        return SFTPStorageConfig(
            host="backup.example.com",
            username="backup_user",
            password="secure_password",
            remote_path="/backups/borg",
            port=2222,
        )

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        """Mock command executor"""
        return AsyncMock(spec=CommandExecutorProtocol)

    @pytest.fixture
    def mock_file_service(self) -> AsyncMock:
        """Mock file service"""
        return AsyncMock(spec=FileServiceProtocol)

    @pytest.fixture
    def sftp_storage(
        self,
        sftp_config: SFTPStorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> SFTPStorage:
        """SFTPStorage instance with mocked dependencies"""
        return SFTPStorage(sftp_config, mock_command_executor, mock_file_service)

    def test_initialization(
        self,
        sftp_config: SFTPStorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> None:
        """Test SFTPStorage initialization"""
        storage = SFTPStorage(sftp_config, mock_command_executor, mock_file_service)

        assert storage._config is sftp_config
        assert storage._command_executor is mock_command_executor
        assert storage._file_service is mock_file_service

    def test_get_connection_info_password_auth(self, sftp_storage: SFTPStorage) -> None:
        """Test getting connection info with password auth"""
        info = sftp_storage.get_connection_info()

        assert isinstance(info, ConnectionInfo)
        assert info.provider == "sftp"
        assert info.details["host"] == "backup.example.com"
        assert info.details["port"] == 2222
        assert info.details["username"] == "backup_user"
        assert info.details["remote_path"] == "/backups/borg"
        assert info.details["auth_method"] == "password"
        assert info.details["host_key_checking"] is True

    def test_get_connection_info_private_key_auth(
        self, mock_command_executor: AsyncMock, mock_file_service: AsyncMock
    ) -> None:
        """Test getting connection info with private key auth"""
        config = SFTPStorageConfig(
            host="backup.example.com",
            username="key_user",
            private_key="-----BEGIN PRIVATE KEY-----\n...",
            remote_path="/backups",
        )
        storage = SFTPStorage(config, mock_command_executor, mock_file_service)

        info = storage.get_connection_info()
        assert info.details["auth_method"] == "private_key"

    def test_get_sensitive_fields(self, sftp_storage: SFTPStorage) -> None:
        """Test getting sensitive field names"""
        fields = sftp_storage.get_sensitive_fields()

        assert fields == ["password", "private_key"]
        assert isinstance(fields, list)

    async def test_upload_repository_success(
        self, sftp_storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        """Test successful repository upload"""

        # Mock successful subprocess
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait = AsyncMock(return_value=0)

        # Create a callable that returns items from a list, then empty bytes
        stdout_responses = [
            b"Transferred: 10% complete\n",
            b"Transferred: 75% complete\n",
        ]
        stdout_iter = iter(stdout_responses)

        async def mock_stdout_readline() -> bytes:
            try:
                return next(stdout_iter)
            except StopIteration:
                return b""

        mock_process.stdout.readline = mock_stdout_readline
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess = AsyncMock(return_value=mock_process)

        events = []

        def progress_callback(event: SyncEvent) -> None:
            events.append(event)

        await sftp_storage.upload_repository("/test/repo", "daily/", progress_callback)

        # Verify events - START + COMPLETED at minimum
        assert len(events) >= 2
        assert events[0].type == SyncEventType.STARTED
        assert "backup.example.com" in events[0].message
        assert events[-1].type == SyncEventType.COMPLETED

    async def test_upload_repository_error(
        self, sftp_storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        """Test upload with error"""

        # Mock subprocess creation that fails
        mock_command_executor.create_subprocess = AsyncMock(
            side_effect=Exception("SSH connection refused")
        )

        events = []

        def progress_callback(event: SyncEvent) -> None:
            events.append(event)

        with pytest.raises(Exception, match="SFTP upload failed"):
            await sftp_storage.upload_repository(
                "/test/repo", "daily/", progress_callback
            )

        # Should have START and at least one ERROR event
        assert len(events) >= 2
        assert events[0].type == SyncEventType.STARTED
        assert any(e.type == SyncEventType.ERROR for e in events)

    async def test_test_connection_success(
        self,
        sftp_storage: SFTPStorage,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> None:
        """Test successful connection test"""
        # Mock successful lsd and write test commands
        mock_command_executor.execute_command = AsyncMock(
            return_value=CommandResult(
                command=["rclone", "lsd", ":sftp:/backups/borg"],
                return_code=0,
                stdout="drwxr-xr-x          - daily",
                stderr="",
                success=True,
                execution_time=1.0,
            )
        )

        # Mock temp file for write test - create a proper async context manager
        from unittest.mock import MagicMock

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value="/tmp/test")
        async_cm.__aexit__ = AsyncMock(return_value=None)
        mock_file_service.create_temp_file = MagicMock(return_value=async_cm)

        result = await sftp_storage.test_connection()

        assert result is True

    async def test_test_connection_failure(
        self, sftp_storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        """Test failed connection test"""
        mock_command_executor.execute_command = AsyncMock(
            return_value=CommandResult(
                command=["rclone", "lsd", ":sftp:/backups/borg"],
                return_code=1,
                stdout="",
                stderr="connection refused",
                success=False,
                execution_time=1.0,
                error="connection refused",
            )
        )

        result = await sftp_storage.test_connection()
        assert result is False

    async def test_test_connection_exception(
        self, sftp_storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        """Test connection test with exception"""
        mock_command_executor.execute_command = AsyncMock(
            side_effect=Exception("Timeout")
        )

        result = await sftp_storage.test_connection()
        assert result is False
