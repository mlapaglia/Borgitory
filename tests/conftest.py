"""
Shared test configuration and fixtures available to all test types.
"""

import os
from typing import AsyncGenerator, Dict
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

if not os.getenv("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from borgitory.dependencies import get_db
from borgitory.main import app
from borgitory.models.database import Base

from tests.fixtures.job_fixtures import (  # noqa: F401
    mock_job_manager,
    job_manager_config,
    sample_repository,
    sample_database_job,
    sample_database_job_with_tasks,
    mock_job_executor,
    sample_borg_job,
    sample_composite_job,
    mock_event_broadcaster,
    mock_job_dependencies,
    mock_subprocess_process,
)

from tests.fixtures.registry_fixtures import (  # noqa: F401
    production_registry,
    clean_registry,
    s3_only_registry,
    sftp_only_registry,
    smb_only_registry,
    notification_registry_factory,
    notification_registry,
    clean_notification_registry,
    pushover_only_notification_registry,
    discord_only_notification_registry,
)


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database with proper isolation."""
    SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestingSessionLocal() as db_session:
            yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with TestingSessionLocal() as test_session:
        try:
            yield test_session
        finally:
            await test_session.rollback()
            await test_session.close()

    await engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture
def mock_rclone_service() -> Mock:
    """Create a mock RcloneService."""
    mock = Mock()

    mock.test_s3_connection.return_value = {
        "status": "success",
        "message": "Connection successful",
    }

    async def mock_sync_generator() -> AsyncGenerator[Dict[str, str], None]:
        yield {"type": "log", "stream": "stdout", "message": "Starting sync"}
        yield {"type": "log", "stream": "stdout", "message": "Syncing files"}
        yield {"type": "completed", "status": "success", "message": "Sync completed"}

    mock.sync_repository_to_s3 = Mock(return_value=mock_sync_generator())

    return mock
