"""
Tests for CheckTaskExecutor: borg check options and the per-policy frequency gate
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Mapping, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.protocols.command_protocols import ProcessResult
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.services.jobs.task_executors.check_task_executor import (
    CheckTaskExecutor,
    build_check_args,
)

JOB_START = datetime(2026, 11, 15, 2, 0, tzinfo=timezone.utc)


class TestBuildCheckArgs:
    @pytest.mark.parametrize(
        "params, expected",
        [
            ({}, []),
            ({"check_type": "full"}, []),
            ({"check_type": "repository_only"}, ["--repository-only"]),
            ({"check_type": "archives_only"}, ["--archives-only"]),
            ({"verify_data": True}, ["--verify-data"]),
            ({"repair_mode": True}, ["--repair"]),
            ({"save_space": True}, ["--save-space"]),
            (
                {"check_type": "repository_only", "max_duration": 3600},
                ["--repository-only", "--max-duration", "3600"],
            ),
            ({"archive_glob": "host-*"}, ["--glob-archives", "host-*"]),
            ({"archive_prefix": "host-"}, ["--glob-archives", "host-*"]),
            (
                {"archive_glob": "glob-*", "archive_prefix": "prefix-"},
                ["--glob-archives", "glob-*"],
            ),
            ({"first_n_archives": 5}, ["--first", "5"]),
            ({"last_n_archives": 3}, ["--last", "3"]),
            # Legacy keys still work
            ({"repository_only": True}, ["--repository-only"]),
            ({"archives_only": True}, ["--archives-only"]),
            ({"repair": True}, ["--repair"]),
            # Empty and invalid values are ignored
            (
                {
                    "max_duration": None,
                    "archive_glob": "",
                    "archive_prefix": None,
                    "first_n_archives": 0,
                    "last_n_archives": None,
                },
                [],
            ),
        ],
    )
    def test_maps_params_to_flags(
        self, params: Mapping[str, object], expected: List[str]
    ) -> None:
        assert build_check_args(params) == expected

    def test_accepts_check_type_enum(self) -> None:
        from borgitory.models.schemas import CheckType

        assert build_check_args({"check_type": CheckType.REPOSITORY_ONLY}) == [
            "--repository-only"
        ]


def _make_executor(
    last_check: Optional[datetime] = None,
    return_code: int = 0,
) -> tuple[CheckTaskExecutor, Mock, Mock]:
    job_executor = Mock()
    job_executor.start_process = AsyncMock(return_value=AsyncMock())
    job_executor.monitor_process_output = AsyncMock(
        return_value=ProcessResult(
            return_code=return_code, stdout=b"", stderr=b"", error=None
        )
    )

    database_manager = Mock()
    database_manager.get_repository_data = AsyncMock(
        return_value={"id": 1, "path": "/tmp/test-repo", "passphrase": "secret"}
    )
    database_manager.get_last_successful_check_job_start = AsyncMock(
        return_value=last_check
    )

    executor = CheckTaskExecutor(
        job_executor=job_executor,
        output_manager=Mock(),
        event_broadcaster=Mock(),
        database_manager=database_manager,
    )
    return executor, job_executor, database_manager


def _make_job(parameters: Mapping[str, object]) -> tuple[BorgJob, BorgJobTask]:
    task = BorgJobTask(
        task_type=TaskTypeEnum.CHECK,
        task_name="Check repo (Biweekly)",
        parameters=dict(parameters),
    )
    job = BorgJob(
        id=uuid.uuid4(),
        job_type=JobTypeEnum.COMPOSITE,
        status=JobStatusEnum.RUNNING,
        started_at=JOB_START,
        tasks=[task],
        repository_id=1,
    )
    return job, task


class TestCheckCommand:
    async def test_passes_policy_options_to_borg(self) -> None:
        executor, job_executor, _ = _make_executor()
        job, task = _make_job(
            {"check_type": "repository_only", "max_duration": 600, "save_space": True}
        )

        assert await executor.execute_check_task(job, task) is True

        command = job_executor.start_process.call_args.args[0]
        assert command[:2] == ["borg", "check"]
        assert "--repository-only" in command
        assert command[command.index("--max-duration") + 1] == "600"
        assert "--save-space" in command
        assert command[-1] == "/tmp/test-repo"

    async def test_repair_confirms_without_prompt(self) -> None:
        executor, job_executor, _ = _make_executor()
        job, task = _make_job({"repair_mode": True})

        await executor.execute_check_task(job, task)

        command, environment = job_executor.start_process.call_args.args
        assert "--repair" in command
        assert environment["BORG_CHECK_I_KNOW_WHAT_I_AM_DOING"] == "YES"

    async def test_no_repair_confirmation_without_repair(self) -> None:
        executor, job_executor, _ = _make_executor()
        job, task = _make_job({"check_type": "full"})

        await executor.execute_check_task(job, task)

        _, environment = job_executor.start_process.call_args.args
        assert "BORG_CHECK_I_KNOW_WHAT_I_AM_DOING" not in environment


class TestCheckFrequency:
    POLICY = {"check_config_id": 7, "frequency_days": 14, "check_type": "full"}

    async def test_runs_when_never_checked(self) -> None:
        executor, job_executor, database_manager = _make_executor(last_check=None)
        job, task = _make_job(self.POLICY)

        assert await executor.execute_check_task(job, task) is True

        database_manager.get_last_successful_check_job_start.assert_awaited_once_with(
            1, 7
        )
        job_executor.start_process.assert_awaited_once()
        assert task.status == TaskStatusEnum.COMPLETED

    async def test_skips_when_checked_recently(self) -> None:
        executor, job_executor, _ = _make_executor(
            last_check=JOB_START - timedelta(days=3)
        )
        job, task = _make_job(self.POLICY)

        assert await executor.execute_check_task(job, task) is True

        job_executor.start_process.assert_not_called()
        assert task.status == TaskStatusEnum.SKIPPED
        assert task.completed_at is not None
        assert task.output_lines
        message = str(task.output_lines[-1])
        assert "every 14 days" in message
        assert "2026-11-26 02:00" in message  # next due

    async def test_runs_on_the_same_clock_time_n_days_later(self) -> None:
        executor, job_executor, _ = _make_executor(
            last_check=JOB_START - timedelta(days=14)
        )
        job, task = _make_job(self.POLICY)

        await executor.execute_check_task(job, task)

        job_executor.start_process.assert_awaited_once()
        assert task.status == TaskStatusEnum.COMPLETED

    async def test_runs_within_grace_of_due_time(self) -> None:
        executor, job_executor, _ = _make_executor(
            last_check=JOB_START - timedelta(days=14) + timedelta(minutes=30)
        )
        job, task = _make_job(self.POLICY)

        await executor.execute_check_task(job, task)

        job_executor.start_process.assert_awaited_once()

    async def test_skips_outside_grace(self) -> None:
        executor, job_executor, _ = _make_executor(
            last_check=JOB_START - timedelta(days=14) + timedelta(hours=2)
        )
        job, task = _make_job(self.POLICY)

        await executor.execute_check_task(job, task)

        job_executor.start_process.assert_not_called()
        assert task.status == TaskStatusEnum.SKIPPED

    async def test_no_frequency_always_runs(self) -> None:
        executor, job_executor, database_manager = _make_executor(
            last_check=JOB_START - timedelta(hours=1)
        )
        job, task = _make_job({"check_config_id": 7, "frequency_days": None})

        await executor.execute_check_task(job, task)

        database_manager.get_last_successful_check_job_start.assert_not_called()
        job_executor.start_process.assert_awaited_once()

    async def test_custom_check_without_policy_always_runs(self) -> None:
        executor, job_executor, database_manager = _make_executor(
            last_check=JOB_START - timedelta(hours=1)
        )
        job, task = _make_job({"frequency_days": 14, "check_type": "full"})

        await executor.execute_check_task(job, task)

        database_manager.get_last_successful_check_job_start.assert_not_called()
        job_executor.start_process.assert_awaited_once()
