"""
Tests that the backup executor passes every source path to borg create.
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
        setattr(deps, "job_executor", mock_executor)

        mock_output_manager = MagicMock()
        mock_output_manager.add_output_line = AsyncMock()
        setattr(deps, "output_manager", mock_output_manager)

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
