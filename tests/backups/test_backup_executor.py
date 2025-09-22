import asyncio
import pytest
from borgitory.utils.datetime_utils import now_utc
from typing import Generator, AsyncGenerator, Any
from unittest.mock import Mock, AsyncMock, patch
from contextlib import contextmanager
from sqlalchemy.orm import Session

from borgitory.services.backups.backup_executor import (
    BackupExecutor,
    BackupConfig,
    PruneConfig,
    BackupResult,
    BackupStatus,
)
from borgitory.models.database import Repository


class TestBackupStatus:
    """Test BackupStatus enum"""

    def test_backup_status_enum_values(self) -> None:
        """Test all backup status enum values"""
        assert BackupStatus.PENDING.value == "pending"
        assert BackupStatus.RUNNING.value == "running"
        assert BackupStatus.COMPLETED.value == "completed"
        assert BackupStatus.FAILED.value == "failed"


class TestBackupConfig:
    """Test BackupConfig dataclass"""

    def test_backup_config_default_values(self) -> None:
        """Test BackupConfig with default values"""
        config = BackupConfig(source_paths=["/data", "/home"])

        assert config.source_paths == ["/data", "/home"]
        assert config.compression == "zstd"
        assert config.excludes == []
        assert config.dry_run is False
        assert config.show_stats is True
        assert config.show_list is True
        assert config.archive_name is not None
        assert "backup-" in config.archive_name

    def test_backup_config_custom_values(self) -> None:
        """Test BackupConfig with custom values"""
        config = BackupConfig(
            source_paths=["/custom"],
            archive_name="custom-archive",
            compression="lz4",
            excludes=["*.tmp", "cache/"],
            dry_run=True,
            show_stats=False,
            show_list=False,
        )

        assert config.source_paths == ["/custom"]
        assert config.archive_name == "custom-archive"
        assert config.compression == "lz4"
        assert config.excludes == ["*.tmp", "cache/"]
        assert config.dry_run is True
        assert config.show_stats is False
        assert config.show_list is False

    def test_backup_config_none_excludes_becomes_empty_list(self) -> None:
        """Test that None excludes becomes empty list"""
        config = BackupConfig(source_paths=["/data"], excludes=None)
        assert config.excludes == []

    def test_backup_config_auto_generated_archive_name(self) -> None:
        """Test archive name auto-generation"""
        config = BackupConfig(source_paths=["/data"], archive_name=None)
        assert config.archive_name is not None
        assert config.archive_name.startswith("backup-")
        assert len(config.archive_name) > 7  # "backup-" + timestamp


class TestPruneConfig:
    """Test PruneConfig dataclass"""

    def test_prune_config_default_values(self) -> None:
        """Test PruneConfig with default values"""
        config = PruneConfig()

        assert config.keep_within is None
        assert config.keep_daily is None
        assert config.keep_weekly is None
        assert config.keep_monthly is None
        assert config.keep_yearly is None
        assert config.dry_run is False
        assert config.show_stats is True
        assert config.show_list is False

    def test_prune_config_custom_values(self) -> None:
        """Test PruneConfig with custom values"""
        config = PruneConfig(
            keep_within="7d",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=2,
            dry_run=True,
            show_stats=False,
            show_list=True,
        )

        assert config.keep_within == "7d"
        assert config.keep_daily == 7
        assert config.keep_weekly == 4
        assert config.keep_monthly == 6
        assert config.keep_yearly == 2
        assert config.dry_run is True
        assert config.show_stats is False
        assert config.show_list is True


class TestBackupResult:
    """Test BackupResult dataclass"""

    def test_backup_result_creation(self) -> None:
        """Test BackupResult creation"""
        started = now_utc()
        completed = now_utc()

        result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=["Archive created successfully"],
            error_message=None,
            started_at=started,
            completed_at=completed,
        )

        assert result.status == BackupStatus.COMPLETED
        assert result.return_code == 0
        assert result.output_lines == ["Archive created successfully"]
        assert result.error_message is None
        assert result.started_at == started
        assert result.completed_at == completed

    def test_backup_result_success_property_true(self) -> None:
        """Test success property returns True for completed with return code 0"""
        result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=0,
            output_lines=[],
        )
        assert result.success is True

    def test_backup_result_success_property_false_failed_status(self) -> None:
        """Test success property returns False for failed status"""
        result = BackupResult(
            status=BackupStatus.FAILED,
            return_code=1,
            output_lines=[],
        )
        assert result.success is False

    def test_backup_result_success_property_false_nonzero_return_code(self) -> None:
        """Test success property returns False for non-zero return code"""
        result = BackupResult(
            status=BackupStatus.COMPLETED,
            return_code=1,
            output_lines=[],
        )
        assert result.success is False

    def test_backup_result_default_values(self) -> None:
        """Test BackupResult with minimal required arguments"""
        result = BackupResult(
            status=BackupStatus.RUNNING,
            return_code=-1,
            output_lines=[],
        )

        assert result.status == BackupStatus.RUNNING
        assert result.return_code == -1
        assert result.output_lines == []
        assert result.error_message is None
        assert result.started_at is None
        assert result.completed_at is None


class TestBackupExecutor:
    """Test BackupExecutor class"""

    @pytest.fixture
    def backup_executor(self) -> BackupExecutor:
        """Create backup executor for testing"""
        return BackupExecutor()

    @pytest.fixture
    def test_repository(self, test_db: Session) -> Generator[Repository, None, None]:
        """Create test repository using real database"""

        @contextmanager
        def db_session_factory() -> Generator[Session, None, None]:
            try:
                yield test_db
            finally:
                pass

        with db_session_factory() as db:
            repo = Repository(
                name="test-backup-repo",
                path="/tmp/test-backup-repo",
                encrypted_passphrase="dummy",  # Will be set properly
            )
            repo.set_passphrase("test-passphrase-123")
            db.add(repo)
            db.commit()
            db.refresh(repo)
            return repo

    def test_backup_executor_initialization(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test BackupExecutor initialization"""
        assert backup_executor.subprocess_executor is not None
        assert backup_executor.progress_pattern is not None
        assert backup_executor.active_operations == {}

    def test_backup_executor_custom_subprocess_executor(self) -> None:
        """Test BackupExecutor with custom subprocess executor"""
        mock_executor = Mock()
        executor = BackupExecutor(subprocess_executor=mock_executor)
        assert executor.subprocess_executor == mock_executor

    def test_get_active_operations_empty(self, backup_executor: BackupExecutor) -> None:
        """Test get_active_operations returns empty list initially"""
        operations = backup_executor.get_active_operations()
        assert operations == []

    def test_is_operation_active_false(self, backup_executor: BackupExecutor) -> None:
        """Test is_operation_active returns False for non-existent operation"""
        assert backup_executor.is_operation_active("nonexistent") is False

    def test_parse_progress_line_borg_pattern(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with Borg progress pattern"""
        # Borg progress line pattern: original_size compressed_size deduplicated_size nfiles path
        line = "1048576 524288 262144 10 /home/user/documents"

        progress = backup_executor._parse_progress_line(line)

        assert progress["original_size"] == 1048576
        assert progress["compressed_size"] == 524288
        assert progress["deduplicated_size"] == 262144
        assert progress["nfiles"] == 10
        assert progress["path"] == "/home/user/documents"
        assert "timestamp" in progress

    def test_parse_progress_line_archive_name(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with archive name"""
        line = "Archive name: backup-20231201-120000"

        progress = backup_executor._parse_progress_line(line)

        assert progress["archive_name"] == "backup-20231201-120000"

    def test_parse_progress_line_fingerprint(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with fingerprint"""
        line = "Archive fingerprint: abc123def456"

        progress = backup_executor._parse_progress_line(line)

        assert progress["fingerprint"] == "abc123def456"

    def test_parse_progress_line_start_time(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with start time"""
        line = "Time (start): Thu, 2023-12-01 12:00:00"

        progress = backup_executor._parse_progress_line(line)

        assert progress["start_time"] == "Thu, 2023-12-01 12:00:00"

    def test_parse_progress_line_end_time(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with end time"""
        line = "Time (end): Thu, 2023-12-01 12:05:00"

        progress = backup_executor._parse_progress_line(line)

        assert progress["end_time"] == "Thu, 2023-12-01 12:05:00"

    def test_parse_progress_line_no_match(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line with line that doesn't match any pattern"""
        line = "Some random log line"

        progress = backup_executor._parse_progress_line(line)

        assert progress == {}

    def test_parse_progress_line_error_handling(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _parse_progress_line handles errors gracefully"""
        # Line that might cause parsing errors
        line = "Archive name: "  # Empty after colon

        progress = backup_executor._parse_progress_line(line)

        # Should handle gracefully and return empty dict or partial data
        assert isinstance(progress, dict)

    def test_build_backup_command(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test _build_backup_command method"""
        config = BackupConfig(
            source_paths=["/data", "/home"],
            archive_name="test-archive",
            compression="zstd",
            excludes=["*.tmp"],
            show_stats=True,
            show_list=True,
        )

        with patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            command, env = backup_executor._build_backup_command(
                test_repository, config
            )

        assert isinstance(command, list)
        assert isinstance(env, dict)
        assert len(command) > 0
        assert "BORG_PASSPHRASE" in env

    def test_build_backup_command_dry_run(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test _build_backup_command with dry run"""
        config = BackupConfig(
            source_paths=["/data"],
            dry_run=True,
        )

        with patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            command, env = backup_executor._build_backup_command(
                test_repository, config
            )

        # Should include --dry-run in additional args somewhere
        assert isinstance(command, list)
        assert isinstance(env, dict)

    def test_build_prune_command(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test _build_prune_command method"""
        config = PruneConfig(
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            show_stats=True,
        )

        with patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            command, env = backup_executor._build_prune_command(test_repository, config)

        assert isinstance(command, list)
        assert isinstance(env, dict)
        assert len(command) > 0
        assert "BORG_PASSPHRASE" in env

    def test_build_prune_command_with_all_retention_options(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test _build_prune_command with all retention options"""
        config = PruneConfig(
            keep_within="7d",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=2,
            dry_run=True,
            show_list=True,
        )

        with patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            command, env = backup_executor._build_prune_command(test_repository, config)

        assert isinstance(command, list)
        assert isinstance(env, dict)

    @pytest.mark.asyncio
    async def test_execute_backup_validation_error(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test execute_backup with validation error"""
        config = BackupConfig(source_paths=[])  # Empty source paths

        result = await backup_executor.execute_backup(test_repository, config)

        assert result.status == BackupStatus.FAILED
        assert result.return_code == -1
        assert result.error_message is not None
        assert "No source paths specified" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_backup_success(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test successful backup execution"""
        config = BackupConfig(source_paths=["/data"])

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Archive created successfully\n", b"Files: 10, Dirs: 2\n"]:
                yield line

        # Mock the subprocess execution
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_backup(test_repository, config)

        assert result.status == BackupStatus.COMPLETED
        assert result.return_code == 0
        assert result.success is True
        assert len(result.output_lines) == 2
        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_backup_failure(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test failed backup execution"""
        config = BackupConfig(source_paths=["/data"])

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Error: Repository not found\n", b"Backup failed\n"]:
                yield line

        # Mock the subprocess execution with failure
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_backup(test_repository, config)

        assert result.status == BackupStatus.FAILED
        assert result.return_code == 1
        assert result.success is False
        assert result.error_message is not None
        assert "Backup failed (exit code 1)" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_backup_with_callbacks(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test backup execution with callbacks"""
        config = BackupConfig(source_paths=["/data"])
        output_lines = []
        progress_data = []

        def output_callback(line: str) -> Any:
            output_lines.append(line)

        def progress_callback(progress: dict) -> Any:
            progress_data.append(progress)

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [
                b"1048576 524288 262144 10 /home/user\n",
                b"Archive name: test-archive\n",
            ]:
                yield line

        # Mock the subprocess execution
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_backup(
                test_repository,
                config,
                output_callback=output_callback,
                progress_callback=progress_callback,
            )

        assert result.status == BackupStatus.COMPLETED
        assert len(output_lines) == 2
        assert len(progress_data) >= 1  # At least one progress update

    @pytest.mark.asyncio
    async def test_execute_backup_exception_handling(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test backup execution exception handling"""
        config = BackupConfig(source_paths=["/data"])

        with patch.object(
            backup_executor, "_start_process", side_effect=Exception("Process failed")
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_backup(test_repository, config)

        assert result.status == BackupStatus.FAILED
        assert result.return_code == -1
        assert result.error_message is not None
        assert "Backup operation failed: Process failed" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_prune_success(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test successful prune execution"""
        config = PruneConfig(keep_daily=7)

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Prune completed successfully\n"]:
                yield line

        # Mock the subprocess execution
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_prune(test_repository, config)

        assert result.status == BackupStatus.COMPLETED
        assert result.return_code == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_prune_failure(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test failed prune execution"""
        config = PruneConfig(keep_daily=7)

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Error: Cannot prune repository\n"]:
                yield line

        # Mock the subprocess execution with failure
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=2)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            result = await backup_executor.execute_prune(test_repository, config)

        assert result.status == BackupStatus.FAILED
        assert result.return_code == 2
        assert result.error_message is not None
        assert "Prune failed (exit code 2)" in result.error_message

    @pytest.mark.asyncio
    async def test_start_process(self, backup_executor: BackupExecutor) -> None:
        """Test _start_process method"""
        command = ["echo", "test"]

        # Mock asyncio.create_subprocess_exec
        mock_process = Mock()
        mock_process.pid = 12345

        with patch.object(
            backup_executor, "subprocess_executor", return_value=mock_process
        ) as mock_exec:
            process = await backup_executor._start_process(command)

        assert process == mock_process
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_process_with_env_and_cwd(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _start_process with environment and working directory"""
        command = ["echo", "test"]
        env = {"TEST": "value"}
        cwd = "/tmp"

        mock_process = Mock()
        mock_process.pid = 12345

        with patch.object(
            backup_executor, "subprocess_executor", return_value=mock_process
        ) as mock_exec:
            process = await backup_executor._start_process(command, env, cwd)

        assert process == mock_process
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_process_exception(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _start_process exception handling"""
        command = ["nonexistent-command"]

        with patch.object(
            backup_executor,
            "subprocess_executor",
            side_effect=Exception("Failed to start"),
        ):
            with pytest.raises(Exception, match="Failed to start"):
                await backup_executor._start_process(command)

    @pytest.mark.asyncio
    async def test_monitor_process_output(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _monitor_process_output method"""

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Line 1\n", b"Line 2\n"]:
                yield line

        mock_process = Mock()
        mock_process.stdout = mock_stdout()

        result = BackupResult(
            status=BackupStatus.RUNNING, return_code=-1, output_lines=[]
        )

        output_data = await backup_executor._monitor_process_output(
            mock_process, result
        )

        assert len(result.output_lines) == 2
        assert result.output_lines[0] == "Line 1"
        assert result.output_lines[1] == "Line 2"
        assert len(output_data) > 0

    @pytest.mark.asyncio
    async def test_monitor_process_output_with_callbacks(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _monitor_process_output with callbacks"""

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"1048576 524288 262144 10 /data\n"]:
                yield line

        mock_process = Mock()
        mock_process.stdout = mock_stdout()

        result = BackupResult(
            status=BackupStatus.RUNNING, return_code=-1, output_lines=[]
        )

        output_callback = Mock()
        progress_callback = Mock()

        await backup_executor._monitor_process_output(
            mock_process, result, output_callback, progress_callback
        )

        output_callback.assert_called()
        progress_callback.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_process_output_exception(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test _monitor_process_output exception handling"""

        # Create a proper async iterator that raises exception on iteration
        class MockStdout:
            def __aiter__(self) -> "MockStdout":
                return self

            async def __anext__(self) -> bytes:
                raise Exception("Read error")

        mock_process = Mock()
        mock_process.stdout = MockStdout()

        result = BackupResult(
            status=BackupStatus.RUNNING, return_code=-1, output_lines=[]
        )

        await backup_executor._monitor_process_output(mock_process, result)

        assert result.error_message is not None
        assert "Process monitoring error" in result.error_message

    @pytest.mark.asyncio
    async def test_terminate_operation_success(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test successful operation termination"""
        operation_id = "test-op-123"

        # Mock process
        mock_process = Mock()
        mock_process.returncode = None
        mock_process.terminate = Mock()
        mock_process.wait = AsyncMock()

        backup_executor.active_operations[operation_id] = mock_process

        result = await backup_executor.terminate_operation(operation_id)

        assert result is True
        assert operation_id not in backup_executor.active_operations
        mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_operation_force_kill(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test operation termination with force kill"""
        operation_id = "test-op-456"

        # Mock process that doesn't terminate gracefully
        mock_process = Mock()
        mock_process.returncode = None
        mock_process.terminate = Mock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = Mock()

        backup_executor.active_operations[operation_id] = mock_process

        # First wait() call times out, second succeeds after kill
        mock_process.wait.side_effect = [asyncio.TimeoutError(), None]

        result = await backup_executor.terminate_operation(operation_id, timeout=0.1)

        assert result is True
        assert operation_id not in backup_executor.active_operations
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_operation_not_found(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test terminating non-existent operation"""
        result = await backup_executor.terminate_operation("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_terminate_operation_already_finished(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test terminating already finished operation"""
        operation_id = "finished-op"

        # Mock process that already finished
        mock_process = Mock()
        mock_process.returncode = 0  # Already finished

        backup_executor.active_operations[operation_id] = mock_process

        result = await backup_executor.terminate_operation(operation_id)

        assert result is True
        assert operation_id not in backup_executor.active_operations

    @pytest.mark.asyncio
    async def test_terminate_operation_exception(
        self, backup_executor: BackupExecutor
    ) -> None:
        """Test terminate_operation exception handling"""
        operation_id = "error-op"

        # Mock process that raises exception
        mock_process = Mock()
        mock_process.returncode = None
        mock_process.terminate = Mock(side_effect=Exception("Terminate failed"))

        backup_executor.active_operations[operation_id] = mock_process

        result = await backup_executor.terminate_operation(operation_id)

        assert result is False

    def test_active_operations_tracking(self, backup_executor: BackupExecutor) -> None:
        """Test active operations tracking"""
        # Initially empty
        assert backup_executor.get_active_operations() == []
        assert backup_executor.is_operation_active("test") is False

        # Add mock operation
        mock_process = Mock()
        backup_executor.active_operations["test-op"] = mock_process

        assert backup_executor.get_active_operations() == ["test-op"]
        assert backup_executor.is_operation_active("test-op") is True
        assert backup_executor.is_operation_active("other") is False

    @pytest.mark.asyncio
    async def test_full_backup_workflow_with_operation_tracking(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test complete backup workflow with operation tracking"""
        config = BackupConfig(source_paths=["/data"])
        operation_id = "backup-workflow-test"

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Archive created successfully\n"]:
                yield line

        # Mock the subprocess execution
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            # Start backup - should track operation
            result = await backup_executor.execute_backup(
                test_repository, config, operation_id=operation_id
            )

        # Operation should be removed after completion
        assert result.status == BackupStatus.COMPLETED
        assert not backup_executor.is_operation_active(operation_id)

    @pytest.mark.asyncio
    async def test_full_prune_workflow_with_operation_tracking(
        self, backup_executor: BackupExecutor, test_repository: Repository
    ) -> None:
        """Test complete prune workflow with operation tracking"""
        config = PruneConfig(keep_daily=7)
        operation_id = "prune-workflow-test"

        # Create a proper async iterator
        async def mock_stdout() -> AsyncGenerator[bytes, None]:
            for line in [b"Prune completed successfully\n"]:
                yield line

        # Mock the subprocess execution
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = mock_stdout()

        with patch.object(
            backup_executor, "_start_process", return_value=mock_process
        ), patch(
            "borgitory.models.database.Repository.get_passphrase",
            return_value="test-passphrase",
        ):
            # Start prune - should track operation
            result = await backup_executor.execute_prune(
                test_repository, config, operation_id=operation_id
            )

        # Operation should be removed after completion
        assert result.status == BackupStatus.COMPLETED
        assert not backup_executor.is_operation_active(operation_id)
