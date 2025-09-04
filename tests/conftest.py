"""
Test configuration and fixtures
"""
import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.database import Base, get_db
from app.services.rclone_service import RcloneService


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
    """Create a test database."""
    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
    
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestingSessionLocal()
    
    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def mock_rclone_service():
    """Create a mock RcloneService."""
    mock = Mock()
    
    # Set up default return values for common methods
    mock.get_configured_remotes.return_value = ["test-remote"]
    mock.test_s3_connection.return_value = {
        "status": "success",
        "message": "Connection successful"
    }
    
    async def mock_sync_generator():
        """Mock async generator for sync progress."""
        yield {"type": "log", "stream": "stdout", "message": "Starting sync"}
        yield {"type": "log", "stream": "stdout", "message": "Syncing files"}
        yield {"type": "completed", "status": "success", "message": "Sync completed"}
    
    mock.sync_repository_to_s3.return_value = mock_sync_generator()
    
    return mock


@pytest.fixture
def async_client(test_db) -> AsyncClient:
    """Create an async test client.""" 
    return AsyncClient(
        transport=ASGITransport(app=app), 
        base_url="http://testserver"
    )


@pytest.fixture
def sample_repository_data():
    """Sample repository data for testing."""
    return {
        "name": "test-repo",
        "path": "/tmp/test-repo", 
        "passphrase": "test-passphrase"
    }


@pytest.fixture
def sample_sync_request():
    """Sample sync request data for testing."""
    return {
        "repository_id": 1,
        "remote_name": "test-config",
        "bucket_name": "test-bucket",
        "path_prefix": "backups/"
    }


@pytest.fixture 
def sample_s3_config():
    """Sample S3 configuration for testing."""
    return {
        "remote_name": "test-s3",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    }