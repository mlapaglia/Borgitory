import pytest
from unittest.mock import AsyncMock
from borgitory.services.cloud_providers.storage.smb_storage import (
    SMBStorageConfig,
    SMBStorage,
)


class TestSMBStorageConfig:
    """Test SMB storage configuration validation"""

    def test_valid_config(self) -> None:
        """Test valid configuration passes validation"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            user="testuser",
            **{"pass": "password123"},
            port=445,
            domain="WORKGROUP",
        )
        assert config.host == "server.example.com"
        assert config.share_name == "backup-share"
        assert config.user == "testuser"
        assert config.pass_ == "password123"
        assert config.port == 445
        assert config.domain == "WORKGROUP"

    def test_default_values(self) -> None:
        """Test default values are set correctly"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
        )
        assert config.user == "guest"
        assert config.port == 445
        assert config.domain == "WORKGROUP"
        assert config.idle_timeout == "1m0s"
        assert config.hide_special_share is True
        assert config.case_insensitive is True
        assert config.use_kerberos is False

    def test_invalid_host(self) -> None:
        """Test invalid host raises validation error"""
        with pytest.raises(ValueError, match="Host cannot start or end with a period"):
            SMBStorageConfig(
                host=".invalid-host",
                share_name="backup-share",
            )

    def test_invalid_host_consecutive_periods(self) -> None:
        """Test host with consecutive periods raises validation error"""
        with pytest.raises(ValueError, match="Host cannot contain consecutive periods"):
            SMBStorageConfig(
                host="invalid..host.com",
                share_name="backup-share",
            )

    def test_invalid_user(self) -> None:
        """Test invalid username raises validation error"""
        with pytest.raises(ValueError, match="Username must contain only"):
            SMBStorageConfig(
                host="server.example.com",
                share_name="backup-share",
                user="invalid@user",
            )

    def test_invalid_share_name(self) -> None:
        """Test invalid share name raises validation error"""
        with pytest.raises(ValueError, match="Share name can only contain"):
            SMBStorageConfig(
                host="server.example.com",
                share_name="invalid/share",
            )

    def test_invalid_domain(self) -> None:
        """Test invalid domain raises validation error"""
        with pytest.raises(ValueError, match="Domain must contain only"):
            SMBStorageConfig(
                host="server.example.com",
                share_name="backup-share",
                domain="invalid@domain",
            )

    def test_invalid_idle_timeout(self) -> None:
        """Test invalid idle timeout raises validation error"""
        with pytest.raises(ValueError, match="Idle timeout must be in duration format"):
            SMBStorageConfig(
                host="server.example.com",
                share_name="backup-share",
                idle_timeout="invalid",
            )

    def test_valid_idle_timeout_formats(self) -> None:
        """Test various valid idle timeout formats"""
        valid_timeouts = ["30s", "1m", "1m30s", "2h", "1h30m", "1h30m45s"]
        for timeout in valid_timeouts:
            config = SMBStorageConfig(
                host="server.example.com",
                share_name="backup-share",
                idle_timeout=timeout,
            )
            assert config.idle_timeout == timeout

    def test_kerberos_with_password_validation(self) -> None:
        """Test that Kerberos and password cannot be used together"""
        with pytest.raises(
            ValueError, match="Cannot use both Kerberos and password authentication"
        ):
            SMBStorageConfig(
                host="server.example.com",
                share_name="backup-share",
                use_kerberos=True,
                **{"pass": "password123"},
            )

    def test_kerberos_without_ccache_allowed(self) -> None:
        """Test that Kerberos without explicit ccache is allowed"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            use_kerberos=True,
        )
        assert config.use_kerberos is True
        assert config.kerberos_ccache is None

    def test_host_normalization(self) -> None:
        """Test that host is normalized to lowercase"""
        config = SMBStorageConfig(
            host="SERVER.EXAMPLE.COM",
            share_name="backup-share",
        )
        assert config.host == "server.example.com"

    def test_domain_normalization(self) -> None:
        """Test that domain is normalized to uppercase"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            domain="workgroup",
        )
        assert config.domain == "WORKGROUP"


class TestSMBStorage:
    """Test SMB storage implementation"""

    @pytest.fixture
    def mock_rclone_service(self):
        return AsyncMock()

    @pytest.fixture
    def storage_config(self):
        return SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            user="testuser",
            **{"pass": "password123"},
            port=445,
            domain="WORKGROUP",
        )

    @pytest.fixture
    def storage(self, storage_config, mock_rclone_service):
        return SMBStorage(storage_config, mock_rclone_service)

    @pytest.mark.asyncio
    async def test_test_connection_success(self, storage, mock_rclone_service) -> None:
        """Test successful connection test"""
        mock_rclone_service.test_smb_connection.return_value = {"status": "success"}

        result = await storage.test_connection()
        assert result is True

        mock_rclone_service.test_smb_connection.assert_called_once_with(
            host="server.example.com",
            user="testuser",
            password="password123",
            port=445,
            domain="WORKGROUP",
            share_name="backup-share",
            spn=None,
            use_kerberos=False,
            idle_timeout="1m0s",
            hide_special_share=True,
            case_insensitive=True,
            kerberos_ccache=None,
        )

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, storage, mock_rclone_service) -> None:
        """Test failed connection test"""
        mock_rclone_service.test_smb_connection.side_effect = Exception(
            "Connection failed"
        )

        result = await storage.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_upload_repository_success(
        self, storage, mock_rclone_service
    ) -> None:
        """Test successful repository upload"""

        # Mock the async generator
        async def mock_sync_generator(*args, **kwargs):
            yield {"type": "progress", "message": "Uploading...", "percentage": 50.0}
            yield {"type": "completed", "message": "Upload complete"}

        mock_rclone_service.sync_repository_to_smb = mock_sync_generator

        progress_events = []

        def progress_callback(event) -> None:
            progress_events.append(event)

        await storage.upload_repository(
            repository_path="/path/to/repo",
            remote_path="backups/test",
            progress_callback=progress_callback,
        )

        # Note: We can't easily assert on the async generator call parameters with this mocking approach
        # The important thing is that the upload completes successfully

        # Verify progress events were fired
        assert len(progress_events) >= 2  # started + completed at minimum
        assert any(event.type.value == "started" for event in progress_events)
        assert any(event.type.value == "completed" for event in progress_events)

    @pytest.mark.asyncio
    async def test_upload_repository_failure(
        self, storage, mock_rclone_service
    ) -> None:
        """Test repository upload failure"""

        async def mock_failing_generator(*args, **kwargs):
            raise Exception("Upload failed")
            yield  # pyright: ignore[reportUnreachable]

        mock_rclone_service.sync_repository_to_smb = mock_failing_generator

        progress_events = []

        def progress_callback(event) -> None:
            progress_events.append(event)

        with pytest.raises(Exception, match="SMB upload failed: Upload failed"):
            await storage.upload_repository(
                repository_path="/path/to/repo",
                remote_path="backups/test",
                progress_callback=progress_callback,
            )

        # Verify error event was fired
        assert any(event.type.value == "error" for event in progress_events)

    def test_get_sensitive_fields(self, storage) -> None:
        """Test sensitive fields are correctly identified"""
        sensitive_fields = storage.get_sensitive_fields()
        assert "pass" in sensitive_fields
        assert len(sensitive_fields) == 1

    def test_get_connection_info(self, storage) -> None:
        """Test connection info formatting"""
        info = storage.get_connection_info()
        assert info.provider == "smb"
        assert info.details["host"] == "server.example.com"
        assert info.details["port"] == 445
        assert info.details["user"] == "testuser"
        assert info.details["domain"] == "WORKGROUP"
        assert info.details["share_name"] == "backup-share"
        assert info.details["auth_method"] == "password"
        assert info.details["case_insensitive"] is True
        assert "***" in info.details["password"]  # Should be masked

    def test_get_connection_info_kerberos(self, mock_rclone_service) -> None:
        """Test connection info formatting with Kerberos"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            use_kerberos=True,
        )
        storage = SMBStorage(config, mock_rclone_service)

        info = storage.get_connection_info()
        assert info.details["auth_method"] == "kerberos"
        assert info.details["password"] is None

    def test_get_connection_info_short_password(self, mock_rclone_service) -> None:
        """Test connection info formatting with short password"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            **{"pass": "123"},
        )
        storage = SMBStorage(config, mock_rclone_service)

        info = storage.get_connection_info()
        assert info.details["password"] == "***"

    def test_get_connection_info_no_password(self, mock_rclone_service) -> None:
        """Test connection info formatting with no password"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
        )
        storage = SMBStorage(config, mock_rclone_service)

        info = storage.get_connection_info()
        assert info.details["password"] is None


class TestSMBStorageAdvancedOptions:
    """Test SMB storage with advanced configuration options"""

    @pytest.fixture
    def mock_rclone_service(self):
        return AsyncMock()

    def test_advanced_config_options(self) -> None:
        """Test configuration with all advanced options"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            user="testuser",
            spn="cifs/server.example.com:1020",
            use_kerberos=False,
            idle_timeout="2h",
            hide_special_share=False,
            case_insensitive=False,
            kerberos_ccache="FILE:/path/to/ccache",
        )

        assert config.spn == "cifs/server.example.com:1020"
        assert config.idle_timeout == "2h"
        assert config.hide_special_share is False
        assert config.case_insensitive is False
        assert config.kerberos_ccache == "FILE:/path/to/ccache"

    @pytest.mark.asyncio
    async def test_upload_with_advanced_options(self, mock_rclone_service) -> None:
        """Test upload with advanced configuration options"""
        config = SMBStorageConfig(
            host="server.example.com",
            share_name="backup-share",
            user="testuser",
            **{"pass": "password123"},
            spn="cifs/server.example.com:1020",
            idle_timeout="2h",
            hide_special_share=False,
            case_insensitive=False,
        )
        storage = SMBStorage(config, mock_rclone_service)

        # Mock the async generator
        async def mock_sync_generator(*args, **kwargs):
            yield {"type": "completed", "message": "Upload complete"}

        mock_rclone_service.sync_repository_to_smb = mock_sync_generator

        await storage.upload_repository(
            repository_path="/path/to/repo", remote_path="backups/test"
        )
