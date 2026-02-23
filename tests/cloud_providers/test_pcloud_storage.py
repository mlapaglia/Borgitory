import pytest
from unittest.mock import AsyncMock

from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.cloud_providers.storage.pcloud_storage import (
    PcloudStorageConfig,
    PcloudStorage,
)
from borgitory.services.cloud_providers.types import SyncEvent
from borgitory.services.cloud_providers.registry import (
    get_supported_providers,
    get_provider_info,
)


VALID_TOKEN_JSON = '{"access_token":"abc123","token_type":"bearer","expiry":"0001-01-01T00:00:00Z"}'


class TestPcloudStorageConfig:
    """Test pCloud storage configuration validation"""

    def test_valid_config(self) -> None:
        config = PcloudStorageConfig(
            token=VALID_TOKEN_JSON,
            hostname="api.pcloud.com",
        )
        assert config.token == VALID_TOKEN_JSON
        assert config.hostname == "api.pcloud.com"
        assert config.root_folder_id is None

    def test_valid_config_with_root_folder(self) -> None:
        config = PcloudStorageConfig(
            token=VALID_TOKEN_JSON,
            hostname="eapi.pcloud.com",
            root_folder_id="d123",
        )
        assert config.hostname == "eapi.pcloud.com"
        assert config.root_folder_id == "d123"

    def test_default_hostname(self) -> None:
        config = PcloudStorageConfig(token=VALID_TOKEN_JSON)
        assert config.hostname == "api.pcloud.com"

    def test_empty_hostname_defaults(self) -> None:
        config = PcloudStorageConfig(token=VALID_TOKEN_JSON, hostname="   ")
        assert config.hostname == "api.pcloud.com"

    def test_hostname_normalized_lowercase(self) -> None:
        config = PcloudStorageConfig(
            token=VALID_TOKEN_JSON,
            hostname="EAPI.PCLOUD.COM",
        )
        assert config.hostname == "eapi.pcloud.com"

    def test_token_required(self) -> None:
        with pytest.raises(ValueError, match="Token is required"):
            PcloudStorageConfig(token="   ")

    def test_token_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Token must be valid JSON"):
            PcloudStorageConfig(token="not json")

    def test_token_missing_access_token_key(self) -> None:
        with pytest.raises(ValueError, match="access_token"):
            PcloudStorageConfig(token='{"other":"value"}')


class TestPcloudStorage:
    """Test pCloud storage implementation"""

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def storage_config(self) -> PcloudStorageConfig:
        return PcloudStorageConfig(
            token=VALID_TOKEN_JSON,
            hostname="api.pcloud.com",
        )

    @pytest.fixture
    def mock_file_service(self) -> AsyncMock:
        return AsyncMock(spec=FileServiceProtocol)

    @pytest.fixture
    def storage(
        self,
        storage_config: PcloudStorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> PcloudStorage:
        return PcloudStorage(
            storage_config, mock_command_executor, mock_file_service
        )

    async def test_test_connection_success(
        self, storage: PcloudStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_command_executor.execute_command.return_value = mock_result

        result = await storage.test_connection()
        assert result is True

    async def test_test_connection_failure(
        self, storage: PcloudStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.execute_command.side_effect = Exception(
            "Connection failed"
        )
        result = await storage.test_connection()
        assert result is False

    async def test_upload_repository_success(
        self, storage: PcloudStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait.return_value = 0
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_process.stdout.readline = AsyncMock(
            side_effect=[b"Transferred: 100%\n", b""]
        )
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess.return_value = mock_process

        progress_events = []

        def progress_callback(event: SyncEvent) -> None:
            progress_events.append(event)

        await storage.upload_repository(
            repository_path="/path/to/repo",
            remote_path="backups/test",
            progress_callback=progress_callback,
        )

        assert len(progress_events) >= 2
        assert any(event.type.value == "started" for event in progress_events)
        assert any(event.type.value == "completed" for event in progress_events)

    async def test_upload_repository_failure(
        self, storage: PcloudStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait.return_value = 1
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        mock_command_executor.create_subprocess.return_value = mock_process

        progress_events = []

        def progress_callback(event: SyncEvent) -> None:
            progress_events.append(event)

        with pytest.raises(Exception, match="pCloud sync failed"):
            await storage.upload_repository(
                repository_path="/path/to/repo",
                remote_path="backups/test",
                progress_callback=progress_callback,
            )
        assert any(event.type.value == "error" for event in progress_events)

    def test_get_sensitive_fields(self, storage: PcloudStorage) -> None:
        sensitive_fields = storage.get_sensitive_fields()
        assert "token" in sensitive_fields
        assert len(sensitive_fields) == 1

    def test_get_connection_info(self, storage: PcloudStorage) -> None:
        info = storage.get_connection_info()
        assert info.provider == "pcloud"
        assert info.details["hostname"] == "api.pcloud.com"
        assert "***" in str(info.details["token"])

    def test_get_connection_info_short_token(
        self, mock_command_executor: AsyncMock, mock_file_service: AsyncMock
    ) -> None:
        short_valid_token = '{"access_token":"ab"}'
        config = PcloudStorageConfig(
            token=short_valid_token,
            hostname="api.pcloud.com",
        )
        storage = PcloudStorage(config, mock_command_executor, mock_file_service)
        info = storage.get_connection_info()
        assert "***" in str(info.details["token"])

    def test_get_display_details(self, storage: PcloudStorage) -> None:
        details = storage.get_display_details(
            {"hostname": "eapi.pcloud.com", "root_folder_id": "d0"}
        )
        assert details["provider_name"] == "pCloud"
        provider_details = details["provider_details"]
        assert isinstance(provider_details, dict)
        assert "hostname" in provider_details
        assert provider_details.get("hostname") == "eapi.pcloud.com"
        assert provider_details.get("root_folder_id") == "d0"

    def test_get_rclone_mapping(self) -> None:
        mapping = PcloudStorage.get_rclone_mapping()
        assert mapping.sync_method == "sync_repository_to_pcloud"
        assert mapping.test_method == "test_pcloud_connection"
        assert "token" in mapping.parameter_mapping
        assert "repository" in mapping.required_params
        assert "token" in mapping.required_params


class TestPcloudRegistry:
    """Test pCloud provider registration"""

    def test_pcloud_in_supported_providers(self) -> None:
        from borgitory.services.cloud_providers.storage import PcloudProvider  # noqa: F401

        providers = get_supported_providers()
        assert "pcloud" in providers

    def test_pcloud_provider_info(self) -> None:
        from borgitory.services.cloud_providers.storage import PcloudProvider  # noqa: F401

        info = get_provider_info("pcloud")
        assert info is not None
        assert info.name == "pcloud"
        assert info.label == "pCloud"
        assert info.config_class == "PcloudStorageConfig"
        assert info.storage_class == "PcloudStorage"
        assert info.supports_encryption is True
        assert info.supports_versioning is False
