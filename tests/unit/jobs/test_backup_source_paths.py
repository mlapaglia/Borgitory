"""
Tests the borg create command built by the backup executor: source paths and compression.
"""

import uuid
from typing import Any, Dict, List, cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.services.jobs.job_manager import JobManager
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    JobManagerDependencies,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.utils.datetime_utils import now_utc


class TestBackupSourcePaths:
    @pytest.fixture
    def job_manager(self) -> JobManager:
        deps: JobManagerDependencies = JobManagerFactory.create_for_testing(
            mock_event_broadcaster=Mock(spec=JobEventBroadcasterProtocol)
        )

        mock_executor = MagicMock()
        mock_executor.start_process = AsyncMock(return_value=MagicMock(pid=12345))
        mock_executor.monitor_process_output = AsyncMock(
            return_value=ProcessResult(
                return_code=0, stdout=b"", stderr=b"", error=None
            )
        )
        deps.job_executor = mock_executor

        mock_output_manager = MagicMock()
        mock_output_manager.add_output_line = AsyncMock()
        deps.output_manager = mock_output_manager

        return JobManager(dependencies=deps)

    @pytest.fixture
    def mock_job(self) -> BorgJob:
        return BorgJob(
            id=uuid.uuid4(),
            job_type=JobTypeEnum.BACKUP,
            repository_id=1,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
        )

    async def run_backup(
        self, job_manager: JobManager, job: BorgJob, parameters: Dict[str, Any]
    ) -> List[str]:
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Backup",
            parameters={"archive_name": "test-archive", **parameters},
        )
        task.output_lines = []

        with patch.object(
            job_manager.backup_executor.database_manager,
            "get_repository_data",
            return_value={"path": "/test/repo", "passphrase": "test-passphrase"},
        ):
            result = await job_manager.backup_executor.execute_backup_task(
                job, task, task_index=0
            )

        assert result is True
        start_process = cast(AsyncMock, job_manager.executor.start_process)
        command: List[str] = start_process.call_args.args[0]
        return command

    async def test_all_source_paths_follow_archive(
        self, job_manager: JobManager, mock_job: BorgJob
    ) -> None:
        command = await self.run_backup(
            job_manager,
            mock_job,
            {"source_paths": ["/appdata/one", "/appdata/two", "/appdata/three"]},
        )

        archive_index = command.index("/test/repo::test-archive")
        assert command[archive_index + 1 :] == [
            "/appdata/one",
            "/appdata/two",
            "/appdata/three",
        ]

    async def test_no_source_paths_adds_nothing_after_archive(
        self, job_manager: JobManager, mock_job: BorgJob
    ) -> None:
        command = await self.run_backup(job_manager, mock_job, {})

        assert command[-1] == "/test/repo::test-archive"

    @pytest.mark.parametrize("compression", ["zstd", "lz4", "zlib", "lzma", "none"])
    async def test_compression_passed_to_borg_create(
        self, job_manager: JobManager, mock_job: BorgJob, compression: str
    ) -> None:
        command = await self.run_backup(
            job_manager,
            mock_job,
            {"source_paths": ["/data"], "compression": compression},
        )

        index = command.index("--compression")
        assert command[index + 1] == compression

    async def test_missing_compression_defaults_to_zstd(
        self, job_manager: JobManager, mock_job: BorgJob
    ) -> None:
        command = await self.run_backup(
            job_manager, mock_job, {"source_paths": ["/data"]}
        )

        index = command.index("--compression")
        assert command[index + 1] == "zstd"

    async def test_invalid_compression_fails_without_running_borg(
        self, job_manager: JobManager, mock_job: BorgJob
    ) -> None:
        task = BorgJobTask(
            task_type=TaskTypeEnum.BACKUP,
            task_name="Backup",
            parameters={
                "archive_name": "test-archive",
                "source_paths": ["/data"],
                "compression": "CompressionType.ZSTD",
            },
        )

        with patch.object(
            job_manager.backup_executor.database_manager,
            "get_repository_data",
            return_value={"path": "/test/repo", "passphrase": "test-passphrase"},
        ):
            result = await job_manager.backup_executor.execute_backup_task(
                mock_job, task, task_index=0
            )

        assert result is False
        assert task.status == TaskStatusEnum.FAILED
        assert task.error is not None
        assert "Invalid compression" in task.error
        cast(AsyncMock, job_manager.executor.start_process).assert_not_called()
