"""
Test configuration and fixtures
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add src directory to Python path for tests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

# Set SECRET_KEY before importing the app to avoid RuntimeError
if not os.getenv("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from main import app
from models.database import Base, get_db

# Import all models to ensure they're registered with Base
# Import job fixtures to make them available to all tests - noqa prevents removal
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


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db():
    """Create a test database with proper isolation."""
    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create ALL tables at once
    Base.metadata.create_all(bind=engine)

    # Create a session for the test
    db_session = TestingSessionLocal()

    def override_get_db():
        try:
            # Use the same session for the entire test
            yield db_session
        finally:
            # Don't close during the test
            pass

    # Set up the dependency override
    app.dependency_overrides[get_db] = override_get_db

    try:
        yield db_session
    finally:
        # Clean up after test
        db_session.rollback()  # Roll back any uncommitted changes
        db_session.close()
        app.dependency_overrides.clear()


@pytest.fixture
def mock_rclone_service():
    """Create a mock RcloneService."""
    mock = Mock()

    # Set up default return values for common methods
    mock.get_configured_remotes.return_value = ["test-remote"]
    mock.test_s3_connection.return_value = {
        "status": "success",
        "message": "Connection successful",
    }

    async def mock_sync_generator():
        """Mock async generator for sync progress."""
        yield {"type": "log", "stream": "stdout", "message": "Starting sync"}
        yield {"type": "log", "stream": "stdout", "message": "Syncing files"}
        yield {"type": "completed", "status": "success", "message": "Sync completed"}

    mock.sync_repository_to_s3.return_value = mock_sync_generator()

    return mock


@pytest_asyncio.fixture
async def async_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with proper resource management."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def sample_repository_data():
    """Sample repository data for testing."""
    return {
        "name": "test-repo",
        "path": "/tmp/test-repo",
        "passphrase": "test-passphrase",
    }


@pytest.fixture
def sample_sync_request():
    """Sample sync request data for testing."""
    return {
        "repository_id": 1,
        "remote_name": "test-config",
        "bucket_name": "test-bucket",
        "path_prefix": "backups/",
    }


@pytest.fixture
def sample_s3_config():
    """Sample S3 configuration for testing."""
    return {
        "remote_name": "test-s3",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }
