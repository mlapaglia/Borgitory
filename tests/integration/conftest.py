"""Integration test fixtures and configuration."""

import pytest
import tempfile
import os
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from borgitory.models.database import Base


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for integration test data."""
    import time

    # Use function scope and unique naming to ensure test isolation
    temp_dir = tempfile.mkdtemp(
        prefix=f"borgitory_integration_{int(time.time() * 1000000)}_"
    )
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_db_path(temp_data_dir):
    """Create a temporary database path for testing."""
    import uuid

    # Use unique database filename to avoid conflicts
    db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"
    db_path = os.path.join(temp_data_dir, db_filename)
    yield db_path
    # Cleanup handled by temp_data_dir fixture


@pytest.fixture
def test_db_engine(temp_db_path):
    """Create a test database engine."""
    engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def test_db_session(test_db_engine):
    """Create a test database session."""
    Base.metadata.create_all(bind=test_db_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_env_vars(temp_data_dir):
    """Set up environment variables for integration tests."""
    import uuid

    original_env = {}

    # Use unique database filename and secret key
    db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"
    secret_key = f"test-secret-key-{uuid.uuid4().hex}"

    test_vars = {
        "BORGITORY_DATA_DIR": temp_data_dir,
        "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(temp_data_dir, db_filename)}",
        "BORGITORY_SECRET_KEY": secret_key,
    }

    # Store original values and set test values
    for key, value in test_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield test_vars

    # Restore original values
    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value
