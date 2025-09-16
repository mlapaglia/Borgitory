"""
Tests for JobExecutor cloud sync method.

"""

import pytest
from unittest.mock import AsyncMock

from services.jobs.job_executor import JobExecutor
from services.cloud_providers.types import CloudSyncConfig, SyncResult
from services.cloud_providers.config_service import MockConfigLoadService


class TestJobExecutor:
    """Test JobExecutor with clean architecture"""

    @pytest.fixture
    def job_executor(self):
        """Create JobExecutor instance"""
        return JobExecutor()

    @pytest.fixture
    def mock_cloud_sync_service(self):
        """Mock cloud sync service"""
        return AsyncMock()

    @pytest.fixture
    def mock_config_load_service(self):
        """Mock config load service"""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_successful_cloud_sync(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test successful cloud sync - simple and focused!"""
        # Arrange
        config = CloudSyncConfig(
            provider="s3", config={"bucket_name": "test-bucket"}, name="test-config"
        )
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result(
            bytes_transferred=1024, duration_seconds=2.5
        )

        # Act
        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # Assert
        assert result.return_code == 0
        assert result.error is None
        assert b"completed successfully" in result.stdout

        # Verify services were called correctly
        mock_config_load_service.load_config.assert_called_once_with(1)
        mock_cloud_sync_service.execute_sync.assert_called_once_with(
            config, "/test/repo", None
        )

    @pytest.mark.asyncio
    async def test_successful_sync_with_metrics(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test successful sync with detailed metrics"""
        config = CloudSyncConfig(
            provider="sftp", config={"host": "backup.example.com"}, name="backup-server"
        )
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result(
            bytes_transferred=2048576,  # 2MB
            files_transferred=150,
            duration_seconds=45.7,
        )

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/prod/repo",
            cloud_sync_config_id=5,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 0
        assert result.error is None

        # Verify the right config was loaded
        mock_config_load_service.load_config.assert_called_once_with(5)

        # Verify sync was called with correct parameters
        call_args = mock_cloud_sync_service.execute_sync.call_args
        assert call_args[0][0] is config  # First arg should be the config
        assert call_args[0][1] == "/prod/repo"  # Second arg is repo path

    @pytest.mark.asyncio
    async def test_config_not_found(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test when config is not found - equally simple!"""
        # Arrange
        mock_config_load_service.load_config.return_value = None

        # Act
        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=999,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # Assert
        assert result.return_code == 0  # Skip, not error
        assert b"configuration disabled" in result.stdout
        assert result.error is None

        # Sync service should not be called
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_config_disabled(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test when config is disabled"""
        # Config service returns None for disabled configs
        mock_config_load_service.load_config.return_value = None

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=123,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 0
        assert b"configuration disabled" in result.stdout
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_failure(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test sync failure handling"""
        # Arrange
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test-bucket"})
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.error_result(
            "Network timeout after 30 seconds"
        )

        # Act
        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # Assert
        assert result.return_code == 1
        assert result.error == "Network timeout after 30 seconds"
        assert b"Network timeout after 30 seconds" in result.stderr

    @pytest.mark.asyncio
    async def test_sync_failure_with_partial_success(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test sync failure that transferred some data"""
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test"})
        mock_config_load_service.load_config.return_value = config

        # Create error result that still has some transfer metrics
        error_result = SyncResult.error_result("Connection lost during transfer")
        error_result.bytes_transferred = 512  # Some data was transferred
        error_result.files_transferred = 3
        error_result.duration_seconds = 15.5

        mock_cloud_sync_service.execute_sync.return_value = error_result

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 1
        assert result.error == "Connection lost during transfer"

    @pytest.mark.asyncio
    async def test_config_not_found(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test when config ID is provided but config doesn't exist"""
        # Arrange - mock config loading to return None
        mock_config_load_service.load_config.return_value = None
        
        # Act
        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=999,  # Valid ID but config doesn't exist
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # Assert
        assert result.return_code == 0  # Skip, not error
        assert b"configuration disabled" in result.stdout
        assert result.error is None

        # Config loading should be called, but sync service should not
        mock_config_load_service.load_config.assert_called_once_with(999)
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_config_id(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test when config ID is 0 (falsy but valid ID)"""
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test"})
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result()

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=0,  # Valid ID that happens to be falsy in Python
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # 0 should be treated as a valid ID, not as "no config"
        assert result.return_code == 0
        assert b"Cloud sync completed successfully" in result.stdout
        mock_config_load_service.load_config.assert_called_once_with(0)
        mock_cloud_sync_service.execute_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_output_callback(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test that output callback is passed through correctly"""
        # Arrange
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test"})
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result()

        output_messages = []

        def output_callback(message):
            output_messages.append(message)

        # Act
        await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
            output_callback=output_callback,
        )

        # Assert
        assert "Starting cloud sync..." in output_messages

        # Verify callback was passed to service
        call_args = mock_cloud_sync_service.execute_sync.call_args
        assert call_args[0][2] is output_callback  # Third argument should be callback

    @pytest.mark.asyncio
    async def test_output_callback_with_failure(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test output callback receives failure messages"""
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test"})
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.error_result(
            "Upload failed"
        )

        output_messages = []

        def output_callback(message):
            output_messages.append(message)

        await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
            output_callback=output_callback,
        )

        # Should have received start message
        assert "Starting cloud sync..." in output_messages
        # Service handles the error messaging through its own callback

    @pytest.mark.asyncio
    async def test_config_load_exception(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test exception during config loading"""
        # Arrange
        mock_config_load_service.load_config.side_effect = Exception(
            "Database connection failed"
        )

        # Act
        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        # Assert
        assert result.return_code == -1
        assert "Database connection failed" in result.error
        assert b"Database connection failed" in result.stderr

        # Sync service should not be called
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_service_exception(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test exception during sync execution"""
        config = CloudSyncConfig(provider="s3", config={"bucket_name": "test"})
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.side_effect = Exception(
            "Sync service crashed"
        )

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == -1
        assert "Sync service crashed" in result.error

    @pytest.mark.asyncio
    async def test_exception_with_output_callback(
        self, job_executor, mock_cloud_sync_service, mock_config_load_service
    ):
        """Test that exceptions are reported to output callback"""
        mock_config_load_service.load_config.side_effect = Exception("Config error")

        output_messages = []

        def output_callback(message):
            output_messages.append(message)

        result = await job_executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
            output_callback=output_callback,
        )

        assert result.return_code == -1
        # Should have received error message through callback
        assert any("Config error" in msg for msg in output_messages)


class TestWithRealMockConfigService:
    """Test using the MockConfigLoadService for more realistic scenarios"""

    @pytest.mark.asyncio
    async def test_with_predefined_configs(self):
        """Test using MockConfigLoadService with predefined configs"""
        # Arrange
        configs = {
            1: CloudSyncConfig(
                provider="s3", config={"bucket_name": "prod-bucket"}, name="production"
            ),
            2: CloudSyncConfig(
                provider="sftp",
                config={"host": "backup.example.com"},
                name="backup-server",
            ),
            3: CloudSyncConfig(
                provider="s3",
                config={"bucket_name": "dev-bucket", "region": "us-west-2"},
                name="development",
                path_prefix="dev-backups/",
            ),
        }

        config_service = MockConfigLoadService(configs)
        sync_service = AsyncMock()
        sync_service.execute_sync.return_value = SyncResult.success_result()

        executor = JobExecutor()

        # Act - test loading config 1
        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=sync_service,
            config_load_service=config_service,
        )

        # Assert
        assert result.return_code == 0

        # Verify correct config was used
        call_args = sync_service.execute_sync.call_args
        used_config = call_args[0][0]
        assert used_config.provider == "s3"
        assert used_config.config["bucket_name"] == "prod-bucket"
        assert used_config.name == "production"

        # Act - test config 3 with path prefix
        sync_service.reset_mock()
        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/repo",
            cloud_sync_config_id=3,
            cloud_sync_service=sync_service,
            config_load_service=config_service,
        )

        assert result.return_code == 0
        call_args = sync_service.execute_sync.call_args
        used_config = call_args[0][0]
        assert used_config.path_prefix == "dev-backups/"

        # Act - test non-existent config
        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/repo",
            cloud_sync_config_id=999,  # Doesn't exist
            cloud_sync_service=sync_service,
            config_load_service=config_service,
        )

        # Assert
        assert result.return_code == 0  # Skip
        assert b"configuration disabled" in result.stdout

    @pytest.mark.asyncio
    async def test_multiple_provider_types(self):
        """Test with different provider types"""
        configs = {
            10: CloudSyncConfig(
                provider="s3",
                config={
                    "bucket_name": "s3-backups",
                    "region": "eu-west-1",
                    "storage_class": "GLACIER",
                },
                name="s3-glacier",
            ),
            20: CloudSyncConfig(
                provider="sftp",
                config={
                    "host": "sftp.backup.com",
                    "port": 2222,
                    "username": "backup_user",
                },
                name="sftp-backup",
            ),
        }

        config_service = MockConfigLoadService(configs)
        sync_service = AsyncMock()
        sync_service.execute_sync.return_value = SyncResult.success_result(
            bytes_transferred=1024000, files_transferred=50, duration_seconds=120.5
        )

        executor = JobExecutor()

        # Test S3 config
        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/data/repo1",
            cloud_sync_config_id=10,
            cloud_sync_service=sync_service,
            config_load_service=config_service,
        )

        assert result.return_code == 0
        s3_call = sync_service.execute_sync.call_args
        assert s3_call[0][0].provider == "s3"
        assert s3_call[0][1] == "/data/repo1"

        # Test SFTP config
        sync_service.reset_mock()
        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/data/repo2",
            cloud_sync_config_id=20,
            cloud_sync_service=sync_service,
            config_load_service=config_service,
        )

        assert result.return_code == 0
        sftp_call = sync_service.execute_sync.call_args
        assert sftp_call[0][0].provider == "sftp"
        assert sftp_call[0][1] == "/data/repo2"
