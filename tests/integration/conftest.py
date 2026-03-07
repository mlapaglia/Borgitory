"""Integration test fixtures and configuration."""

import json
import os
import shutil
import tempfile
import uuid
from typing import Any, AsyncGenerator, Dict, Generator, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from borgitory.api.auth import get_current_user
from borgitory.main import app
from borgitory.models.database import Base, CloudSyncConfig, User


@pytest.fixture
def temp_data_dir() -> Generator[str, None, None]:
    """Create a temporary directory for integration test data."""
    import time

    temp_dir = tempfile.mkdtemp(
        prefix=f"borgitory_integration_{int(time.time() * 1000000)}_"
    )
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_db_path(temp_data_dir: str) -> Generator[str, None, None]:
    """Create a temporary database path for testing."""
    db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"
    db_path = os.path.join(temp_data_dir, db_filename)
    yield db_path


@pytest.fixture
def test_db_engine(temp_db_path: str) -> Generator[Engine, None, None]:
    """Create a test database engine."""
    engine = create_engine(f"sqlite:///{temp_db_path}", echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def test_db_session(test_db_engine: Engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    Base.metadata.create_all(bind=test_db_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_env_vars(temp_data_dir: str) -> Generator[dict[str, str], None, None]:
    """Set up environment variables for integration tests."""
    original_env: dict[str, str | None] = {}

    db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"
    secret_key = f"test-secret-key-{uuid.uuid4().hex}"

    test_vars = {
        "BORGITORY_DATA_DIR": temp_data_dir,
        "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(temp_data_dir, db_filename)}",
        "BORGITORY_SECRET_KEY": secret_key,
    }

    for key, value in test_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield test_vars

    for key, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


@pytest_asyncio.fixture
async def async_client(test_db: Session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with proper resource management and authentication."""
    test_user = User()
    test_user.username = "test_user"
    test_user.set_password("test_password")
    test_db.add(test_user)
    await test_db.commit()
    await test_db.refresh(test_user)

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client

    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest_asyncio.fixture
async def async_client_without_auth(test_db: Session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client without authentication."""
    test_user = User()
    test_user.username = "test_user"
    test_user.set_password("test_password")
    test_db.add(test_user)
    await test_db.commit()
    await test_db.refresh(test_user)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def async_client_without_auth_or_user(test_db: Session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client without authentication and without creating a user."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def sample_repository_data() -> Dict[str, str]:
    """Sample repository data for testing."""
    return {
        "name": "test-repo",
        "path": "/tmp/test-repo",
        "passphrase": "test-passphrase",
    }


@pytest.fixture
def sample_sync_request() -> Dict[str, Any]:
    """Sample sync request data for testing."""
    return {
        "repository_id": 1,
        "remote_name": "test-config",
        "bucket_name": "test-bucket",
        "path_prefix": "backups/",
    }


@pytest.fixture
def sample_s3_config() -> Dict[str, str]:
    """Sample S3 configuration for testing."""
    return {
        "remote_name": "test-s3",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }


def create_cloud_sync_config_with_json(
    name: str,
    provider: str,
    provider_config: Dict[str, Any],
    enabled: bool = True,
    path_prefix: str = "",
    **kwargs: Any,
) -> CloudSyncConfig:
    """Helper function to create CloudSyncConfig with JSON provider_config."""
    config = CloudSyncConfig()
    config.name = name
    config.provider = provider
    config.provider_config = json.dumps(provider_config)
    config.enabled = enabled
    config.path_prefix = path_prefix
    return config


def create_s3_cloud_sync_config(
    name: str = "test-s3",
    bucket_name: str = "test-bucket",
    access_key: str = "test_access_key",
    secret_key: str = "test_secret_key",
    enabled: bool = True,
    **kwargs: Any,
) -> CloudSyncConfig:
    """Helper to create S3 CloudSyncConfig with proper JSON structure."""
    s3_config = {
        "bucket_name": bucket_name,
        "access_key": access_key,
        "secret_key": secret_key,
    }
    return create_cloud_sync_config_with_json(
        name=name, provider="s3", provider_config=s3_config, enabled=enabled, **kwargs
    )


def create_sftp_cloud_sync_config(
    name: str = "test-sftp",
    host: str = "sftp.example.com",
    port: int = 22,
    username: str = "testuser",
    password: Optional[str] = None,
    private_key: Optional[str] = None,
    remote_path: str = "/backups",
    enabled: bool = True,
    **kwargs: Any,
) -> CloudSyncConfig:
    """Helper to create SFTP CloudSyncConfig with proper JSON structure."""
    sftp_config = {
        "host": host,
        "port": port,
        "username": username,
        "remote_path": remote_path,
    }

    if password:
        sftp_config["password"] = password
    if private_key:
        sftp_config["private_key"] = private_key

    return create_cloud_sync_config_with_json(
        name=name,
        provider="sftp",
        provider_config=sftp_config,
        enabled=enabled,
        **kwargs,
    )
