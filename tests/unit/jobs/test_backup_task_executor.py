"""
Tests for BackupTaskExecutor - specifically multi-source-path handling.

Verifies that single paths, JSON array paths, and legacy plain strings
are all correctly expanded into borg create command arguments.
"""

import uuid
from unittest.mock import Mock, AsyncMock, patch

from borgitory.services.jobs.task_executors.backup_task_executor import (
    BackupTaskExecutor,
)
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskTypeEnum,
)
from borgitory.models.job_results import JobStatusEnum
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import BorgCommandResult


def _make_executor() -> tuple[BackupTaskExecutor, Mock, Mock, Mock, Mock]:
    job_executor = Mock()
    job_executor.start_process = AsyncMock()
    job_executor.monitor_process_output = AsyncMock()

    output_manager = Mock()
    output_manager.add_output_line = AsyncMock()

    event_broadcaster = Mock()
    event_broadcaster.broadcast_event = Mock()

    database_manager = Mock()
    database_manager.get_repository_data = AsyncMock()

    executor = BackupTaskExecutor(
        job_executor=job_executor,
        output_manager=output_manager,
        event_broadcaster=event_broadcaster,
        database_manager=database_manager,
    )
    return executor, job_executor, output_manager, event_broadcaster, database_manager


def _make_job_and_task(
    source_path: str,
    archive_name: str = "test-archive",
    repo_id: int = 1,
) -> tuple[BorgJob, BorgJobTask]:
    task = BorgJobTask(
        task_type=TaskTypeEnum.BACKUP,
        task_name="Test Backup",
        parameters={
            "source_path": source_path,
            "archive_name": archive_name,
        },
    )
    job = BorgJob(
        id=uuid.uuid4(),
        job_type="composite",
        status=JobStatusEnum.RUNNING,
        started_at=now_utc(),
        tasks=[task],
        repository_id=repo_id,
    )
    return job, task


def _setup_successful_run(
    job_executor: Mock,
    database_manager: Mock,
) -> None:
    database_manager.get_repository_data.return_value = {
        "id": 1,
        "path": "/tmp/test-repo",
        "passphrase": "test-pass",
    }

    mock_process = AsyncMock()
    mock_process.pid = 12345
    job_executor.start_process.return_value = mock_process

    job_executor.monitor_process_output.return_value = ProcessResult(
        return_code=0,
        stdout=b"Archive created successfully",
        stderr=b"",
        error=None,
    )


class TestBackupTaskExecutorSourcePaths:
    """Verify that source_path values are correctly expanded in the borg command."""

    async def test_single_legacy_path(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(source_path="/data")
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        assert "/data" in args
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == ["/data"]

    async def test_multiple_paths_json_array(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(
            source_path='["/home/user/src", "/home/user/Documents"]'
        )
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            result = await executor.execute_backup_task(job, task)

        assert result is True
        args = captured_args[0]
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == ["/home/user/src", "/home/user/Documents"]

    async def test_three_paths(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(
            source_path='["/appdata/app1", "/appdata/app2", "/appdata/app3"]'
        )
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == ["/appdata/app1", "/appdata/app2", "/appdata/app3"]

    async def test_single_path_json_array(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(source_path='["/data"]')
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == ["/data"]

    async def test_empty_source_path_appends_nothing(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(source_path="")
        task.parameters["source_path"] = ""
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == []

    async def test_no_source_path_key_appends_nothing(self) -> None:
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Test Backup",
            parameters={"archive_name": "test-archive"},
        )
        job = BorgJob(
            id=uuid.uuid4(),
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        repo_archive_idx = next(
            i for i, a in enumerate(args) if "test-repo::test-archive" in a
        )
        path_args = args[repo_archive_idx + 1 :]
        assert path_args == []

    async def test_paths_appear_after_archive_argument(self) -> None:
        """borg create requires paths AFTER repo::archive."""
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        job, task = _make_job_and_task(
            source_path='["/src", "/docs"]'
        )
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        archive_idx = next(
            i for i, a in enumerate(args) if "::" in a
        )
        assert args[archive_idx + 1] == "/src"
        assert args[archive_idx + 2] == "/docs"
        assert len(args) == archive_idx + 3

    async def test_paths_with_patterns_and_dry_run(self) -> None:
        """Multiple paths should coexist with --pattern and --dry-run flags."""
        executor, job_executor, _, _, database_manager = _make_executor()
        _setup_successful_run(job_executor, database_manager)
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Test Backup",
            parameters={
                "source_path": '["/data", "/backup"]',
                "archive_name": "test-archive",
                "patterns": ["+*.txt", "-*.log"],
                "dry_run": True,
            },
        )
        job = BorgJob(
            id=uuid.uuid4(),
            job_type="composite",
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )
        captured_args: list[list[str]] = []

        with patch(
            "borgitory.services.jobs.task_executors.backup_task_executor.create_borg_command"
        ) as mock_cmd:
            mock_cmd.side_effect = lambda **kwargs: (
                captured_args.append(kwargs.get("additional_args", [])),
                BorgCommandResult(command=["borg", "create"], environment={}),
            )[1]

            await executor.execute_backup_task(job, task)

        args = captured_args[0]
        assert "--pattern=+*.txt" in args
        assert "--pattern=-*.log" in args
        assert "--dry-run" in args

        archive_idx = next(i for i, a in enumerate(args) if "::" in a)
        path_args = args[archive_idx + 1 :]
        assert path_args == ["/data", "/backup"]
