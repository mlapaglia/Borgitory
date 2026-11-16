"""Long-running servers must not accumulate jobs or task output forever."""

import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest

from borgitory.models.job_results import JobStatusEnum
from borgitory.services.jobs.job_manager import (
    FINISHED_JOB_RETENTION,
    JobManager,
)
from borgitory.services.jobs.job_manager_factory import JobManagerFactory
from borgitory.services.jobs.job_models import (
    MAX_TASK_OUTPUT_LINES,
    BorgJob,
    BorgJobTask,
    TaskTypeEnum,
)
from borgitory.utils.datetime_utils import now_utc


@pytest.fixture
def job_manager(mock_output_manager: Mock) -> JobManager:
    deps = JobManagerFactory.create_for_testing()
    deps.output_manager = mock_output_manager
    return JobManager(dependencies=deps)


def _job(status: JobStatusEnum, completed_ago: timedelta | None) -> BorgJob:
    now = now_utc()
    return BorgJob(
        id=uuid.uuid4(),
        status=status,
        started_at=now - timedelta(hours=5),
        completed_at=None if completed_ago is None else now - completed_ago,
    )


def test_evicts_only_old_finished_jobs(job_manager: JobManager) -> None:
    old_done = _job(JobStatusEnum.COMPLETED, FINISHED_JOB_RETENTION * 2)
    old_failed = _job(JobStatusEnum.FAILED, FINISHED_JOB_RETENTION * 2)
    recent_done = _job(JobStatusEnum.COMPLETED, timedelta(minutes=1))
    running = _job(JobStatusEnum.RUNNING, None)
    for job in (old_done, old_failed, recent_done, running):
        job_manager.jobs[job.id] = job

    assert job_manager._evict_finished_jobs() == 2
    assert set(job_manager.jobs) == {recent_done.id, running.id}


def test_task_output_is_bounded() -> None:
    task = BorgJobTask(task_type=TaskTypeEnum.BACKUP, task_name="backup")
    for i in range(MAX_TASK_OUTPUT_LINES + 50):
        task.output_lines.append(f"line {i}")

    assert len(task.output_lines) == MAX_TASK_OUTPUT_LINES
    assert task.output_lines[-1] == f"line {MAX_TASK_OUTPUT_LINES + 49}"


def test_task_output_list_is_coerced_to_bounded_buffer() -> None:
    task = BorgJobTask(
        task_type=TaskTypeEnum.BACKUP, task_name="backup", output_lines=["a", "b"]
    )
    assert list(task.output_lines) == ["a", "b"]
    assert task.output_lines.maxlen == MAX_TASK_OUTPUT_LINES
