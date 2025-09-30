"""Integration tests for database migrations using CLI commands."""

import pytest
import subprocess
import os
import tempfile
import shutil
from typing import Generator

@pytest.fixture
def temp_data_dir() -> Generator[str, None, None]:
    """Create a temporary directory for integration test data."""
    # Use a more unique prefix with timestamp to avoid conflicts
    import time

    temp_dir = tempfile.mkdtemp(
        prefix=f"borgitory_migration_{int(time.time() * 1000000)}_"
    )
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def migration_env(temp_data_dir: str) -> dict[str, str]:
    """Set up environment variables for migration testing."""
    env = os.environ.copy()

    # Use a unique database filename to avoid any potential conflicts
    import uuid

    db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"

    env.update(
        {
            "BORGITORY_DATA_DIR": temp_data_dir,
            "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(temp_data_dir, db_filename)}",
            "BORGITORY_SECRET_KEY": f"test-secret-key-{uuid.uuid4().hex}",
        }
    )
    return env

def test_borgitory_command_available() -> None:
    """Test that the borgitory CLI command is available."""
    # Test that borgitory command exists and shows help
    result = subprocess.run(
        ["borgitory", "--help"], capture_output=True, text=True, timeout=10
    )

    assert result.returncode == 0, (
        f"borgitory --help failed with exit code {result.returncode}"
    )


def test_borgitory_version_command() -> None:
    """Test that borgitory --version works."""
    result = subprocess.run(
        ["borgitory", "--version"], capture_output=True, text=True, timeout=10
    )

    assert result.returncode == 0, (
        f"borgitory --version failed with exit code {result.returncode}"
    )
