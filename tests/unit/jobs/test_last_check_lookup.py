"""
Tests for recording a job's check policy and looking up the last successful check,
against a real (in-memory) database
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from borgitory.models.database import (
    Base,
    Job,
    JobTask,
    Repository,
    RepositoryCheckConfig,
    StringUUID,
)
from borgitory.models.enums import EncryptionType
from borgitory.models.job_results import JobStatusEnum
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.services.jobs.job_database_manager import (
    DatabaseJobData,
    JobDatabaseManager,
)
from borgitory.services.jobs.job_manager import _check_config_id_of
from borgitory.services.jobs.job_models import TaskTypeEnum

BASE_TIME = datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session_maker() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        for repo_id in (1, 2):
            repo = Repository()
            repo.id = repo_id
            repo.name = f"repo-{repo_id}"
            repo.path = f"/repos/{repo_id}"
            repo.encryption_type = EncryptionType.NONE
            db.add(repo)
        for config_id in (10, 20):
            config = RepositoryCheckConfig()
            config.id = config_id
            config.name = f"policy-{config_id}"
            config.check_type = "full"
            db.add(config)
        await db.commit()

    yield maker
    await engine.dispose()


async def _add_job(
    maker: async_sessionmaker[AsyncSession],
    started_at: datetime,
    repository_id: int = 1,
    check_config_id: Optional[int] = 10,
    task_type: str = "check",
    task_status: str = "completed",
) -> None:
    async with maker() as db:
        job = Job()
        job.id = StringUUID(uuid.uuid4().hex)
        job.repository_id = repository_id
        job.type = "Scheduled Backup"
        job.status = "completed"
        job.job_type = "composite"
        job.started_at = started_at
        job.check_config_id = check_config_id
        db.add(job)

        task = JobTask()
        task.job_id = job.id
        task.task_type = task_type
        task.task_name = "task"
        task.status = task_status
        task.task_order = 0
        db.add(task)
        await db.commit()


class TestLastSuccessfulCheckLookup:
    async def test_none_without_history(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        manager = JobDatabaseManager(async_session_maker=session_maker)

        assert await manager.get_last_successful_check_job_start(1, 10) is None

    async def test_returns_latest_successful_check_as_utc(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        await _add_job(session_maker, BASE_TIME)
        await _add_job(session_maker, BASE_TIME + timedelta(days=14))
        manager = JobDatabaseManager(async_session_maker=session_maker)

        result = await manager.get_last_successful_check_job_start(1, 10)

        assert result == BASE_TIME + timedelta(days=14)
        assert result is not None and result.tzinfo is not None

    async def test_ignores_unrelated_jobs(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        await _add_job(session_maker, BASE_TIME)
        later = BASE_TIME + timedelta(days=5)
        await _add_job(session_maker, later, task_status="failed")
        await _add_job(session_maker, later, task_status="skipped")
        await _add_job(session_maker, later, check_config_id=20)
        await _add_job(session_maker, later, repository_id=2)
        await _add_job(session_maker, later, task_type="backup")
        await _add_job(session_maker, later, check_config_id=None)
        manager = JobDatabaseManager(async_session_maker=session_maker)

        assert await manager.get_last_successful_check_job_start(1, 10) == BASE_TIME


class TestRecordingCheckPolicy:
    async def test_create_database_job_stores_check_config_id(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        manager = JobDatabaseManager(async_session_maker=session_maker)
        job_id = uuid.uuid4()

        await manager.create_database_job(
            DatabaseJobData(
                id=job_id,
                repository_id=1,
                job_type="Scheduled Backup",
                status=JobStatusEnum.PENDING,
                started_at=BASE_TIME,
                check_config_id=10,
            )
        )

        async with session_maker() as db:
            stored = (
                await db.execute(select(Job.check_config_id).where(Job.id == job_id))
            ).scalar_one()
        assert stored == 10

    def test_check_config_id_comes_from_the_check_task(self) -> None:
        tasks = [
            TaskDefinition(type=TaskTypeEnum.BACKUP, name="Backup"),
            TaskDefinition(
                type=TaskTypeEnum.CHECK,
                name="Check",
                parameters={"check_config_id": 10, "frequency_days": 14},
            ),
        ]

        assert _check_config_id_of(tasks) == 10

    def test_no_check_config_id_for_custom_or_missing_check(self) -> None:
        custom_check = TaskDefinition(
            type=TaskTypeEnum.CHECK, name="Check", parameters={"check_type": "full"}
        )
        backup = TaskDefinition(type=TaskTypeEnum.BACKUP, name="Backup")

        assert _check_config_id_of([custom_check]) is None
        assert _check_config_id_of([backup]) is None
