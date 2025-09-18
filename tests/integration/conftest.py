"""Integration test fixtures and configuration."""

import pytest
import tempfile
import os
import shutil
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from borgitory.models.database import Base


@pytest.fixture(scope="session")
def temp_data_dir():
    """Create a temporary directory for integration test data."""
    temp_dir = tempfile.mkdtemp(prefix="borgitory_integration_")
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_db_path(temp_data_dir):
    """Create a temporary database path for testing."""
    db_path = os.path.join(temp_data_dir, "test_borgitory.db")
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
    original_env = {}
    test_vars = {
        "BORGITORY_DATA_DIR": temp_data_dir,
        "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(temp_data_dir, 'test_borgitory.db')}",
        "BORGITORY_SECRET_KEY": "test-secret-key-for-integration-tests-only",
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
