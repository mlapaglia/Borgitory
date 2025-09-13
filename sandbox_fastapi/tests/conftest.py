"""
Test configuration following SQLAlchemy 2.0 and FastAPI best practices.

Provides proper test database isolation and dependency overrides.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.models.repository import Base
from app.dependencies import get_db


# Test database setup with proper isolation
@pytest.fixture(scope="function")
def test_engine():
    """Create test database engine with in-memory SQLite."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Disable SQL logging in tests
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def test_session(test_engine):
    """Create test database session with proper transaction isolation."""
    SessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False
    )
    
    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="function")
def test_client(test_session):
    """Create test client with database dependency override."""
    def override_get_db():
        try:
            yield test_session
            test_session.commit()
        except Exception:
            test_session.rollback()
            raise
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def setup_logging():
    """Set up proper logging for tests."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Reduce noise from SQLAlchemy in tests
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)