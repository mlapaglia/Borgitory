"""
Shared test fixtures for job-related testing.

This module provides standardized pytest fixtures and factories for testing
job services with clean dependency injection patterns.
"""

import pytest
import uuid
from borgitory.utils.datetime_utils import now_utc
from unittest.mock import Mock, AsyncMock
from typing import Any, AsyncGenerator, Dict, List
from sqlalchemy.orm import Session

from borgitory.services.jobs.job_manager import BorgJob, BorgJobTask, JobManagerConfig
from borgitory.models.database import Repository, Job, JobTask


@pytest.fixture
def mock_job_manager() -> Mock:
    """Standard mock JobManager for all job service tests."""
    manager = Mock()
    manager.jobs = {}
    manager.config = JobManagerConfig()
    manager.get_job_status = Mock(return_value=None)
    manager.cleanup_job = Mock(return_value=True)
    manager.cancel_job = AsyncMock(return_value=True)
    manager.get_queue_stats = Mock(
        return_value={
            "max_concurrent_backups": 5,
            "running_backups": 0,
            "queued_backups": 0,
            "available_slots": 5,
        }
    )
    manager.subscribe_to_events = Mock(return_value=AsyncMock())
    manager.unsubscribe_from_events = Mock()
    manager.broadcast_job_event = Mock()
    manager.start_borg_command = AsyncMock(return_value="test-job-id")
    manager.stream_all_job_updates = AsyncMock()
    return manager


@pytest.fixture
def mock_job_executor() -> Mock:
    """Standard mock JobExecutor for job execution tests."""
    executor = Mock()
    executor.start_process = AsyncMock()
    executor.monitor_process_output = AsyncMock()
    executor.terminate_process = AsyncMock(return_value=True)
    executor.parse_progress_line = Mock(return_value={})
    executor.format_command_for_logging = Mock(side_effect=lambda cmd: " ".join(cmd))
    return executor


@pytest.fixture
def sample_borg_job() -> BorgJob:
    """Create a sample BorgJob for testing."""
    return BorgJob(
        id=str(uuid.uuid4()),
        status="completed",
        started_at=now_utc(),
        completed_at=now_utc(),
        command=["borg", "create", "repo::archive", "/data"],
        return_code=0,
        repository_id=1,
    )


@pytest.fixture
def sample_composite_job() -> BorgJob:
    """Create a composite BorgJob with tasks for testing."""
    job_id = str(uuid.uuid4())
    task1 = BorgJobTask(
        task_type="backup",
        task_name="Backup Task",
        status="completed",
        parameters={"source_path": "/data"},
    )
    task2 = BorgJobTask(
        task_type="prune",
        task_name="Prune Task",
        status="completed",
        parameters={"keep_daily": 7},
    )

    return BorgJob(
        id=job_id,
        status="completed",
        started_at=now_utc(),
        completed_at=now_utc(),
        job_type="composite",
        tasks=[task1, task2],
        repository_id=1,
    )


@pytest.fixture
def sample_repository(test_db: Session) -> Repository:
    """Create a sample repository in the test database."""
    repository = Repository()
    repository.name = "test-repo"
    repository.path = "/tmp/test-repo"
    repository.encrypted_passphrase = "test-encrypted-passphrase"
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    return repository


@pytest.fixture
def sample_database_job(test_db: Session, sample_repository: Repository) -> Job:
    """Create a sample Job record in the test database."""
    job = Job()
    job.id = str(uuid.uuid4())
    job.repository_id = sample_repository.id
    job.type = "backup"
    job.status = "completed"
    job.started_at = now_utc()
    job.finished_at = now_utc()
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.fixture
def sample_database_job_with_tasks(
    test_db: Session, sample_repository: Repository
) -> Job:
    """Create a Job with JobTasks in the test database."""
    job = Job()
    job.id = str(uuid.uuid4())
    job.repository_id = sample_repository.id
    job.type = "backup"
    job.status = "completed"
    job.started_at = now_utc()
    job.finished_at = now_utc()
    test_db.add(job)
    test_db.flush()  # Get the job ID

    task1 = JobTask()
    task1.job_id = job.id
    task1.task_type = "backup"
    task1.task_name = "Backup Task"
    task1.task_order = 0
    task1.status = "completed"
    task1.return_code = 0
    task1.output = "Backup completed successfully\nFiles processed: 100"
    task2 = JobTask()
    task2.job_id = job.id
    task2.task_type = "prune"
    task2.task_name = "Prune Task"
    task2.task_order = 1
    task2.status = "completed"
    task2.return_code = 0
    task2.output = "Prune completed\nRemoved 5 archives"

    test_db.add_all([task1, task2])
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.fixture
def job_manager_config() -> JobManagerConfig:
    """Standard JobManagerConfig for testing."""
    return JobManagerConfig(
        max_concurrent_backups=2,
        max_output_lines_per_job=100,
        queue_poll_interval=0.1,
        sse_keepalive_timeout=30.0,
    )


@pytest.fixture
def mock_subprocess_process() -> AsyncMock:
    """Mock subprocess process for job execution testing."""
    process = AsyncMock()
    process.pid = 12345
    process.returncode = None
    process.wait = AsyncMock(return_value=0)
    process.terminate = Mock()
    process.kill = Mock()

    # Mock stdout as async iterator
    async def mock_stdout() -> AsyncGenerator[bytes, None]:
        yield b"Starting backup...\n"
        yield b"Processing files...\n"
        yield b"Backup completed\n"

    process.stdout = mock_stdout()
    return process


def create_mock_job_context(
    job_id: str = "",
    status: str = "completed",
    job_type: str = "simple",
    tasks: List[Dict[str, Any]] = [],
) -> Dict[str, Any]:
    """Factory function to create mock job context for rendering tests."""

    mock_job = Mock()
    mock_job.id = job_id
    mock_job.status = status
    mock_job.job_type = job_type
    mock_job.type = "backup"
    mock_job.started_at = now_utc()
    mock_job.finished_at = now_utc()
    mock_job.return_code = 0
    mock_job.error = None
    mock_job.tasks = tasks or []

    # Mock repository
    mock_repository = Mock()
    mock_repository.name = "Test Repository"
    mock_job.repository = mock_repository

    # Add the job_uuid property for backward compatibility
    mock_job.job_uuid = job_id

    return {
        "job": mock_job,
        "templates_dir": "src/borgitory/templates",
        "current_task": tasks[0] if tasks else None,
        "show_output": False,
    }


def create_mock_event_queue() -> AsyncMock:
    """Factory function to create mock event queue for streaming tests."""
    queue = AsyncMock()
    queue.get = AsyncMock()
    queue.put_nowait = Mock()
    return queue


@pytest.fixture
def mock_event_broadcaster() -> Mock:
    """Mock event broadcaster for job event testing."""
    broadcaster = Mock()
    broadcaster.broadcast_event = Mock()
    broadcaster.subscribe_client = Mock()
    broadcaster.unsubscribe_client = Mock()
    broadcaster.get_client_queues = Mock(return_value={})
    return broadcaster


@pytest.fixture
def mock_job_dependencies() -> Dict[str, Any]:
    """Mock all job-related dependencies in one fixture."""
    return {
        "job_manager": Mock(),
        "job_executor": Mock(),
        "event_broadcaster": Mock(),
        "job_queue_manager": Mock(),
        "composite_job_manager": Mock(),
    }
