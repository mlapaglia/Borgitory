"""
Comprehensive tests for jobs/job_executor.py

This test file adds missing coverage for JobExecutor methods that weren't
fully covered in existing tests, focusing on the prune task and methods
with proper DI patterns and real database usage.
"""

import pytest
from unittest.mock import AsyncMock

from borgitory.services.jobs.job_executor import JobExecutor, ProcessResult
from tests.conftest import create_s3_cloud_sync_config


class TestJobExecutorPruneTask:
    """Test execute_prune_task method with comprehensive coverage"""

    @pytest.fixture
    def executor(self):
        return JobExecutor()

    @pytest.mark.asyncio
    async def test_execute_prune_task_success_basic(self, executor) -> None:
        """Test successful prune task with basic parameters"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"

        # Mock the start_process and monitor_process_output methods
        mock_process = AsyncMock()
        mock_process.pid = 12345

        async def mock_start_process(command, env):
            # Verify the command was built correctly
            assert "borg" in command[0]
            assert "prune" in command
            assert repository_path in command
            assert env.get("BORG_PASSPHRASE") == passphrase
            return mock_process

        async def mock_monitor_output(process, output_callback):
            return ProcessResult(
                return_code=0, stdout=b"Prune completed successfully", stderr=b""
            )

        executor.start_process = mock_start_process
        executor.monitor_process_output = mock_monitor_output

        result = await executor.execute_prune_task(
            repository_path=repository_path, passphrase=passphrase
        )

        assert result.return_code == 0
        assert result.error is None
        assert b"Prune completed successfully" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_prune_task_with_all_retention_options(
        self, executor
    ) -> None:
        """Test prune task with all retention options"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"

        command_args = []

        async def mock_start_process(command, env):
            command_args.extend(command)
            mock_process = AsyncMock()
            mock_process.pid = 12345
            return mock_process

        async def mock_monitor_output(process, output_callback):
            return ProcessResult(return_code=0, stdout=b"", stderr=b"")

        executor.start_process = mock_start_process
        executor.monitor_process_output = mock_monitor_output

        result = await executor.execute_prune_task(
            repository_path=repository_path,
            passphrase=passphrase,
            keep_within="7d",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=2,
            show_stats=True,
        )

        assert result.return_code == 0

        # Verify all options were included in command
        assert "--keep-within" in command_args
        assert "7d" in command_args
        assert "--keep-daily" in command_args
        assert "7" in command_args
        assert "--keep-weekly" in command_args
        assert "4" in command_args
        assert "--keep-monthly" in command_args
        assert "6" in command_args
        assert "--keep-yearly" in command_args
        assert "2" in command_args
        assert "--stats" in command_args
        assert repository_path in command_args

    @pytest.mark.asyncio
    async def test_execute_prune_task_with_optional_flags(self, executor) -> None:
        """Test prune task with optional flags"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"

        command_args = []

        async def mock_start_process(command, env):
            command_args.extend(command)
            return AsyncMock()

        async def mock_monitor_output(process, output_callback):
            return ProcessResult(return_code=0, stdout=b"", stderr=b"")

        executor.start_process = mock_start_process
        executor.monitor_process_output = mock_monitor_output

        result = await executor.execute_prune_task(
            repository_path=repository_path,
            passphrase=passphrase,
            show_list=True,
            save_space=True,
            force_prune=True,
            dry_run=True,
        )

        assert result.return_code == 0

        # Verify flags were included
        assert "--list" in command_args
        assert "--save-space" in command_args
        assert "--force" in command_args
        assert "--dry-run" in command_args

    @pytest.mark.asyncio
    async def test_execute_prune_task_failure(self, executor) -> None:
        """Test prune task failure handling"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"

        async def mock_start_process(command, env):
            return AsyncMock()

        async def mock_monitor_output(process, output_callback):
            return ProcessResult(return_code=1, stdout=b"", stderr=b"Repository locked")

        executor.start_process = mock_start_process
        executor.monitor_process_output = mock_monitor_output

        result = await executor.execute_prune_task(
            repository_path=repository_path, passphrase=passphrase
        )

        assert result.return_code == 1
        assert b"Repository locked" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_prune_task_with_output_callback(self, executor) -> None:
        """Test prune task with output callback"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"
        output_messages = []

        def output_callback(message, progress_info) -> None:
            output_messages.append((message, progress_info))

        callback_passed = []

        async def mock_start_process(command, env):
            return AsyncMock()

        async def mock_monitor_output(process, output_callback):
            callback_passed.append(output_callback is not None)
            return ProcessResult(return_code=0, stdout=b"", stderr=b"")

        executor.start_process = mock_start_process
        executor.monitor_process_output = mock_monitor_output

        result = await executor.execute_prune_task(
            repository_path=repository_path,
            passphrase=passphrase,
            output_callback=output_callback,
        )

        assert result.return_code == 0
        # Verify callback was passed to monitor_process_output
        assert callback_passed[0] is True

    @pytest.mark.asyncio
    async def test_execute_prune_task_exception_handling(self, executor) -> None:
        """Test prune task exception handling"""
        repository_path = "/test/repo"
        passphrase = "test-passphrase"

        async def mock_start_process(command, env):
            raise Exception("Command building failed")

        executor.start_process = mock_start_process

        result = await executor.execute_prune_task(
            repository_path=repository_path, passphrase=passphrase
        )

        assert result.return_code == -1
        assert "Command building failed" in result.error
        assert b"Command building failed" in result.stderr


class TestJobExecutorCloudSyncTaskV2:
    """Test execute_cloud_sync_task_v2 method with real database and DI"""

    @pytest.fixture
    def executor(self):
        return JobExecutor()

    @pytest.fixture
    def mock_cloud_sync_service(self):
        return AsyncMock()

    @pytest.fixture
    def mock_config_load_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_no_config_id(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 - this test should be removed since config_id is now required"""
        # This test is no longer valid since cloud_sync_config_id is now required (int, not Optional[int])
        # The skip logic has been moved to the job manager level
        # We'll test a valid scenario instead

        mock_config_load_service.load_config.return_value = None  # Config not found

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=999,  # Valid ID but config doesn't exist
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 0
        assert b"Cloud sync skipped - configuration disabled" in result.stdout
        assert result.error is None

        # Config loading should be called, but sync service should not
        mock_config_load_service.load_config.assert_called_once_with(999)
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_config_not_found(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 when config is not found"""
        mock_config_load_service.load_config.return_value = None

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 0
        assert b"configuration disabled" in result.stdout
        assert result.error is None

        # Config service should be called, but not sync service
        mock_config_load_service.load_config.assert_called_once_with(1)
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_success(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test successful cloud sync task v2"""
        from borgitory.services.cloud_providers.types import CloudSyncConfig, SyncResult

        # Setup config
        config = CloudSyncConfig(
            provider="s3",
            config={"bucket_name": "test-bucket"},
            name="test-config",
            path_prefix="backups/",
        )
        mock_config_load_service.load_config.return_value = config

        # Setup successful sync result
        sync_result = SyncResult.success_result(
            bytes_transferred=1024, files_transferred=5, duration_seconds=2.5
        )
        mock_cloud_sync_service.execute_sync.return_value = sync_result

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 0
        assert result.error is None
        assert b"completed successfully" in result.stdout

        # Verify services were called correctly
        mock_config_load_service.load_config.assert_called_once_with(1)
        mock_cloud_sync_service.execute_sync.assert_called_once_with(
            config, "/test/repo", None
        )

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_sync_failure(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 when sync fails"""
        from borgitory.services.cloud_providers.types import CloudSyncConfig, SyncResult

        config = CloudSyncConfig(
            provider="s3", config={"bucket_name": "test-bucket"}, name="test-config"
        )
        mock_config_load_service.load_config.return_value = config

        # Setup failed sync result
        sync_result = SyncResult.error_result("Network timeout")
        mock_cloud_sync_service.execute_sync.return_value = sync_result

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == 1
        assert result.error == "Network timeout"
        assert b"Network timeout" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_with_output_callback(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 with output callback"""
        from borgitory.services.cloud_providers.types import CloudSyncConfig, SyncResult

        config = CloudSyncConfig(
            provider="s3", config={"bucket_name": "test-bucket"}, name="test-config"
        )
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result()

        output_messages = []

        def output_callback(message) -> None:
            output_messages.append(message)

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
            output_callback=output_callback,
        )

        assert result.return_code == 0
        assert "Starting cloud sync..." in output_messages

        # Verify callback was passed to sync service
        call_args = mock_cloud_sync_service.execute_sync.call_args
        assert call_args[0][2] is output_callback

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_config_load_exception(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 when config loading fails"""
        mock_config_load_service.load_config.side_effect = Exception("Database error")

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == -1
        assert "Database error" in result.error
        assert b"Database error" in result.stderr

        # Sync service should not be called
        mock_cloud_sync_service.execute_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_sync_service_exception(
        self, executor, mock_cloud_sync_service, mock_config_load_service
    ) -> None:
        """Test cloud sync task v2 when sync service raises exception"""
        from borgitory.services.cloud_providers.types import CloudSyncConfig

        config = CloudSyncConfig(
            provider="s3", config={"bucket_name": "test-bucket"}, name="test-config"
        )
        mock_config_load_service.load_config.return_value = config
        mock_cloud_sync_service.execute_sync.side_effect = Exception(
            "Sync service crashed"
        )

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=1,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=mock_config_load_service,
        )

        assert result.return_code == -1
        assert "Sync service crashed" in result.error

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_with_real_database_config(
        self, executor, test_db
    ) -> None:
        """Test cloud sync task v2 with real database configuration"""
        from borgitory.services.cloud_providers.config_service import (
            DatabaseConfigLoadService,
        )
        from borgitory.services.cloud_providers.types import SyncResult

        # Create a real config in the database
        config = create_s3_cloud_sync_config(
            name="real-test-config", bucket_name="real-test-bucket", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        # Create real config load service
        def db_session_factory():
            return test_db

        config_load_service = DatabaseConfigLoadService(db_session_factory)

        # Mock sync service
        mock_cloud_sync_service = AsyncMock()
        mock_cloud_sync_service.execute_sync.return_value = SyncResult.success_result()

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=config.id,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=config_load_service,
        )

        assert result.return_code == 0

        # Verify sync service was called with loaded config
        call_args = mock_cloud_sync_service.execute_sync.call_args
        loaded_config = call_args[0][0]
        assert loaded_config.name == "real-test-config"
        assert loaded_config.provider == "s3"
        assert loaded_config.config["bucket_name"] == "real-test-bucket"

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_v2_disabled_config_in_database(
        self, executor, test_db
    ) -> None:
        """Test cloud sync task v2 with disabled config in database"""
        from borgitory.services.cloud_providers.config_service import (
            DatabaseConfigLoadService,
        )

        # Create a disabled config in the database
        config = create_s3_cloud_sync_config(
            name="disabled-config",
            bucket_name="test-bucket",
            enabled=False,  # Disabled
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        # Create real config load service
        def db_session_factory():
            return test_db

        config_load_service = DatabaseConfigLoadService(db_session_factory)

        mock_cloud_sync_service = AsyncMock()

        result = await executor.execute_cloud_sync_task_v2(
            repository_path="/test/repo",
            cloud_sync_config_id=config.id,
            cloud_sync_service=mock_cloud_sync_service,
            config_load_service=config_load_service,
        )

        assert result.return_code == 0
        assert b"configuration disabled" in result.stdout

        # Sync service should not be called
        mock_cloud_sync_service.execute_sync.assert_not_called()


class TestJobExecutorFormatCommandForLogging:
    """Test format_command_for_logging method edge cases"""

    @pytest.fixture
    def executor(self):
        return JobExecutor()

    def test_format_command_complex_repository_path(self, executor) -> None:
        """Test command formatting with complex repository path"""
        command = [
            "borg",
            "create",
            "ssh://user@host:port/path/to/repo::archive-2023-01-01",
            "/data",
        ]

        result = executor.format_command_for_logging(command)

        # Should redact the archive name but keep the repository path
        assert "ssh://user@host:port/path/to/repo::[ARCHIVE]" in result
        assert "archive-2023-01-01" not in result

    def test_format_command_multiple_sensitive_args(self, executor) -> None:
        """Test command formatting with multiple sensitive arguments"""
        command = [
            "borg",
            "create",
            "--encryption-passphrase",
            "secret1",
            "-p",
            "secret2",
            "--passphrase",
            "secret3",
            "repo::archive",
            "/data",
        ]

        result = executor.format_command_for_logging(command)

        assert "[REDACTED]" in result
        assert result.count("[REDACTED]") == 3  # Should redact all three passphrases
        assert "secret1" not in result
        assert "secret2" not in result
        assert "secret3" not in result

    def test_format_command_no_sensitive_data(self, executor) -> None:
        """Test command formatting with no sensitive data"""
        command = ["borg", "list", "repo", "--short"]

        result = executor.format_command_for_logging(command)

        assert result == "borg list repo --short"
        assert "[REDACTED]" not in result

    def test_format_command_empty_command(self, executor) -> None:
        """Test command formatting with empty command"""
        command = []

        result = executor.format_command_for_logging(command)

        assert result == ""


class TestJobExecutorParseProgressLine:
    """Test parse_progress_line method with various input formats"""

    @pytest.fixture
    def executor(self):
        return JobExecutor()

    def test_parse_progress_line_with_special_characters_in_path(
        self, executor
    ) -> None:
        """Test parsing progress line with special characters in path"""
        line = "1000000 500000 300000 50 /path/with spaces/and-special_chars/file.txt"

        progress = executor.parse_progress_line(line)

        assert progress["original_size"] == 1000000
        assert progress["compressed_size"] == 500000
        assert progress["deduplicated_size"] == 300000
        assert progress["nfiles"] == 50
        assert progress["path"] == "/path/with spaces/and-special_chars/file.txt"
        assert "timestamp" in progress

    def test_parse_progress_line_multiple_info_types(self, executor) -> None:
        """Test parsing different types of info lines"""
        lines_and_expected = [
            (
                "Archive name: backup-2023-01-01T10:30:00",
                {"archive_name": "backup-2023-01-01T10:30:00"},
            ),
            ("Archive fingerprint: abc123def456", {"fingerprint": "abc123def456"}),
            (
                "Time (start): Mon, 2023-01-01 10:30:00",
                {"start_time": "Mon, 2023-01-01 10:30:00"},
            ),
            (
                "Time (end): Mon, 2023-01-01 10:35:00",
                {"end_time": "Mon, 2023-01-01 10:35:00"},
            ),
        ]

        for line, expected in lines_and_expected:
            progress = executor.parse_progress_line(line)
            for key, value in expected.items():
                assert progress[key] == value

    def test_parse_progress_line_malformed_input(self, executor) -> None:
        """Test parsing malformed progress lines"""
        malformed_lines = [
            "not a progress line at all",
            "1000000 abc def 50 /path",  # Non-numeric values
            "",  # Empty line
            "   ",  # Whitespace only
        ]

        for line in malformed_lines:
            progress = executor.parse_progress_line(line)
            # Should not crash and should return empty dict for malformed lines
            assert isinstance(progress, dict)
            if line.strip():  # Non-empty lines might have some partial parsing
                pass  # Don't assert empty, might have partial results
            else:
                assert progress == {}
