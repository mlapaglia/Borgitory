"""Integration tests for database migrations using CLI commands."""

import pytest
import subprocess
import os
import tempfile
import shutil


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for integration test data."""
    temp_dir = tempfile.mkdtemp(prefix="borgitory_migration_")
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def migration_env(temp_data_dir):
    """Set up environment variables for migration testing."""
    env = os.environ.copy()
    env.update(
        {
            "BORGITORY_DATA_DIR": temp_data_dir,
            "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(temp_data_dir, 'test_borgitory.db')}",
            "BORGITORY_SECRET_KEY": "test-secret-key-for-integration-tests-only",
        }
    )
    return env


def test_migration_command_succeeds(migration_env, temp_data_dir):
    """Test that the migration command runs successfully."""
    # Run migration command
    result = subprocess.run(
        ["borgitory", "migrate"],
        env=migration_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Should succeed
    assert result.returncode == 0, (
        f"Migration failed with exit code {result.returncode}"
    )


def test_migration_command_is_idempotent(migration_env, temp_data_dir):
    """Test that running migration command multiple times is safe."""
    # Run migration first time
    result1 = subprocess.run(
        ["borgitory", "migrate"],
        env=migration_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result1.returncode == 0, (
        f"First migration failed with exit code {result1.returncode}"
    )

    # Run migration second time
    result2 = subprocess.run(
        ["borgitory", "migrate"],
        env=migration_env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result2.returncode == 0, (
        f"Second migration failed with exit code {result2.returncode}"
    )


def test_migration_with_missing_data_dir(migration_env):
    """Test that migration creates data directory if it doesn't exist."""
    # Use a non-existent data directory
    nonexistent_dir = "/tmp/borgitory_test_nonexistent"
    migration_env["BORGITORY_DATA_DIR"] = nonexistent_dir
    migration_env["BORGITORY_DATABASE_URL"] = (
        f"sqlite:///{nonexistent_dir}/test_borgitory.db"
    )

    # Clean up if it exists from previous test
    if os.path.exists(nonexistent_dir):
        shutil.rmtree(nonexistent_dir)

    try:
        # Run migration
        result = subprocess.run(
            ["borgitory", "migrate"],
            env=migration_env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed
        assert result.returncode == 0, (
            f"Migration failed with exit code {result.returncode}"
        )

    finally:
        # Clean up
        if os.path.exists(nonexistent_dir):
            shutil.rmtree(nonexistent_dir, ignore_errors=True)


def test_borgitory_command_available():
    """Test that the borgitory CLI command is available."""
    # Test that borgitory command exists and shows help
    result = subprocess.run(
        ["borgitory", "--help"], capture_output=True, text=True, timeout=10
    )

    assert result.returncode == 0, (
        f"borgitory --help failed with exit code {result.returncode}"
    )


def test_borgitory_version_command():
    """Test that borgitory --version works."""
    result = subprocess.run(
        ["borgitory", "--version"], capture_output=True, text=True, timeout=10
    )

    assert result.returncode == 0, (
        f"borgitory --version failed with exit code {result.returncode}"
    )
