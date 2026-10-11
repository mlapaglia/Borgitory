import pytest
from unittest.mock import AsyncMock, MagicMock
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.services.cloud_providers.storage.sftp_storage import (
    SFTPStorageConfig,
    SFTPStorage,
)
from borgitory.services.cloud_providers.types import SyncEvent


class TestSFTPStorage:
    """Test SFTP storage runtime behavior"""

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_file_service(self) -> AsyncMock:
        return AsyncMock(spec=FileServiceProtocol)

    @pytest.fixture
    def storage_config(self) -> SFTPStorageConfig:
        return SFTPStorageConfig(
            host="nas.example.com",
            username="backup",
            remote_path="/backups",
            password="secret",
            port=22,
        )

    @pytest.fixture
    def storage(
        self,
        storage_config: SFTPStorageConfig,
        mock_command_executor: AsyncMock,
        mock_file_service: AsyncMock,
    ) -> SFTPStorage:
        return SFTPStorage(storage_config, mock_command_executor, mock_file_service)

    def _make_mock_process(self, return_code: int = 0) -> AsyncMock:
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_process.wait.return_value = return_code
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        return mock_process

    def test_get_sensitive_fields(self, storage: SFTPStorage) -> None:
        assert "password" in storage.get_sensitive_fields()
        assert "private_key" in storage.get_sensitive_fields()

    def test_get_connection_info(self, storage: SFTPStorage) -> None:
        info = storage.get_connection_info()
        assert info.provider == "sftp"
        assert info.details["host"] == "nas.example.com"
        assert info.details["port"] == 22
        assert info.details["username"] == "backup"
        assert info.details["remote_path"] == "/backups"
        assert info.details["auth_method"] == "password"

    def test_get_connection_info_private_key(
        self, mock_command_executor: AsyncMock, mock_file_service: AsyncMock
    ) -> None:
        config = SFTPStorageConfig(
            host="nas.example.com",
            username="backup",
            remote_path="/backups",
            private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfakekey\n-----END OPENSSH PRIVATE KEY-----",
        )
        storage = SFTPStorage(config, mock_command_executor, mock_file_service)
        info = storage.get_connection_info()
        assert info.details["auth_method"] == "private_key"

    async def test_upload_repository_success(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            0
        )

        progress_events = []

        def progress_callback(event: SyncEvent) -> None:
            progress_events.append(event)

        await storage.upload_repository(
            repository_path="/path/to/repo",
            remote_path="backups/test",
            progress_callback=progress_callback,
        )

        assert any(event.type.value == "started" for event in progress_events)
        assert any(event.type.value == "completed" for event in progress_events)

    async def test_upload_repository_failure(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            1
        )

        with pytest.raises(Exception, match="SFTP sync failed"):
            await storage.upload_repository(
                repository_path="/path/to/repo",
                remote_path="backups/test",
                progress_callback=lambda e: None,
            )

    async def test_sync_does_not_include_hashcheck_flag_by_default(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            0
        )

        async for _ in storage.sync_repository_to_sftp(
            repository=MagicMock(path="/repo"),
            host="nas.example.com",
            username="backup",
            remote_path="/backups",
            password="secret",
            disable_hashcheck=False,
        ):
            pass

        call_args = mock_command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]
        assert "--sftp-disable-hashcheck" not in command

    async def test_sync_includes_hashcheck_flag_when_disabled(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            0
        )

        async for _ in storage.sync_repository_to_sftp(
            repository=MagicMock(path="/repo"),
            host="nas.example.com",
            username="backup",
            remote_path="/backups",
            password="secret",
            disable_hashcheck=True,
        ):
            pass

        call_args = mock_command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]
        assert "--sftp-disable-hashcheck" in command

    async def test_upload_repository_with_disable_checksums_config(
        self, mock_command_executor: AsyncMock, mock_file_service: AsyncMock
    ) -> None:
        config = SFTPStorageConfig(
            host="nas.example.com",
            username="backup",
            remote_path="/backups",
            password="secret",
            disable_server_side_checksums=True,
        )
        storage = SFTPStorage(config, mock_command_executor, mock_file_service)
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            0
        )

        await storage.upload_repository(
            repository_path="/path/to/repo",
            remote_path="backups/test",
        )

        call_args = mock_command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]
        assert "--sftp-disable-hashcheck" in command

    async def test_upload_repository_without_disable_checksums_config(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.create_subprocess.return_value = self._make_mock_process(
            0
        )

        await storage.upload_repository(
            repository_path="/path/to/repo",
            remote_path="backups/test",
        )

        call_args = mock_command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]
        assert "--sftp-disable-hashcheck" not in command

    async def test_test_connection_success(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_command_executor.execute_command.return_value = mock_result

        result = await storage.test_connection()
        assert result is True

    async def test_test_connection_failure(
        self, storage: SFTPStorage, mock_command_executor: AsyncMock
    ) -> None:
        mock_command_executor.execute_command.side_effect = Exception(
            "Connection refused"
        )

        result = await storage.test_connection()
        assert result is False
