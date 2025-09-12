"""
Proof of concept: Clean FastAPI dependency injection testing.

This demonstrates the proper way to test FastAPI services using
the official dependency override system.
"""

import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime

from app.main import app
from app.services.interfaces import RepositoryQueryService
from app.dependencies_clean import get_repository_query_service
from app.models.database import Repository


class FakeRepositoryQueryService:
    """
    Fake repository query service following 2024 best practices.
    
    This is a 'fake' not a 'mock' - it has working implementation behavior
    but uses a simple in-memory list instead of database queries.
    """
    
    def __init__(self, repositories=None):
        self.repositories = repositories or []
        self.calls = []  # For verifying test behavior
    
    def list_repositories(self, db: Session, skip: int = 0, limit: int = 100):
        """Fake implementation that behaves like real service."""
        self.calls.append(('list_repositories', skip, limit))
        # Simulate pagination behavior
        return self.repositories[skip:skip+limit]


class TestCleanFastAPIDI:
    """Test clean FastAPI dependency injection."""

    def setup_method(self):
        """Clear dependency overrides before each test."""
        app.dependency_overrides.clear()

    def teardown_method(self):
        """Clean up after each test."""
        app.dependency_overrides.clear()

    def test_list_repositories_with_clean_di_override(self, test_db: Session):
        """Test list repositories using clean FastAPI dependency override with real Repository objects."""
        
        # Arrange: Create real Repository objects in test database (2024 best practice)
        repo1 = Repository(name="repo-1", path="/mnt/repo-1")
        repo1.set_passphrase("test-pass-1")
        repo2 = Repository(name="repo-2", path="/mnt/repo-2") 
        repo2.set_passphrase("test-pass-2")
        
        test_db.add_all([repo1, repo2])
        test_db.commit()
        test_db.refresh(repo1)
        test_db.refresh(repo2)
        
        # Create fake service with real Repository objects
        fake_service = FakeRepositoryQueryService([repo1, repo2])
        
        # Use FastAPI's official dependency override system
        app.dependency_overrides[get_repository_query_service] = lambda: fake_service
        
        client = TestClient(app)
        
        # Act: Call the endpoint
        response = client.get("/api/repositories/")
        
        # Assert: Verify behavior
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "repo-1"
        assert data[1]["name"] == "repo-2"
        
        # Verify service was called correctly
        assert len(fake_service.calls) == 1
        assert fake_service.calls[0] == ('list_repositories', 0, 100)

    def test_list_repositories_pagination_with_clean_di(self, test_db: Session):
        """Test pagination using clean dependency injection with real Repository objects."""
        
        # Arrange: Create real Repository objects in test database
        repos = []
        for i in range(10):
            repo = Repository(name=f"repo-{i}", path=f"/mnt/repo-{i}")
            repo.set_passphrase(f"pass-{i}")
            repos.append(repo)
        
        test_db.add_all(repos)
        test_db.commit()
        for repo in repos:
            test_db.refresh(repo)
        
        # Create fake service with real Repository objects
        fake_service = FakeRepositoryQueryService(repos)
        
        # Override using FastAPI's official system
        app.dependency_overrides[get_repository_query_service] = lambda: fake_service
        
        client = TestClient(app)
        
        # Act: Test pagination
        response = client.get("/api/repositories/?skip=2&limit=3")
        
        # Assert: Should get repos 2, 3, 4
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["name"] == "repo-2"
        assert data[1]["name"] == "repo-3"
        assert data[2]["name"] == "repo-4"
        
        # Verify pagination parameters passed correctly
        assert fake_service.calls[0] == ('list_repositories', 2, 3)

    def test_service_layer_independently(self):
        """Test the service layer completely independently."""
        
        # Arrange: Mock database session
        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        # Create real Repository object for more realistic testing
        test_repo = Repository(name="test-repo", path="/mnt/test")
        test_repo.set_passphrase("test-pass")
        mock_query.all.return_value = [test_repo]
        
        # Create service directly
        from app.services.implementations import DefaultRepositoryQueryService
        service = DefaultRepositoryQueryService()
        
        # Act: Call service method directly
        result = service.list_repositories(mock_db, skip=5, limit=10)
        
        # Assert: Verify DB calls
        mock_db.query.assert_called_once_with(Repository)
        mock_query.offset.assert_called_once_with(5)
        mock_query.limit.assert_called_once_with(10)
        mock_query.all.assert_called_once()
        assert len(result) == 1
        assert result[0].name == "test-repo"


def test_clean_di_benefits():
    """
    Demonstrate the benefits of clean FastAPI DI:
    
    BEFORE (our old approach):
    - Global state management
    - Manual override functions
    - Complex bridging between systems
    
    AFTER (FastAPI official pattern):
    - Native FastAPI dependency system
    - Built-in app.dependency_overrides
    - Clean, simple, follows documentation
    """
    
    # Test different service behaviors easily using real Repository objects
    test_scenarios = []
    
    # Empty scenario
    test_scenarios.append(("empty", []))
    
    # Single repo scenario
    single_repo = Repository(name="single-repo", path="/mnt/single")
    single_repo.set_passphrase("pass")
    test_scenarios.append(("single", [single_repo]))
    
    # Multiple repos scenario  
    multiple_repos = []
    for i in range(3):
        repo = Repository(name=f"repo-{i}", path=f"/mnt/repo-{i}")
        repo.set_passphrase(f"pass-{i}")
        multiple_repos.append(repo)
    test_scenarios.append(("multiple", multiple_repos))
    
    for scenario, repos in test_scenarios:
        # Clean setup using FastAPI's official override system with fake service
        fake_service = FakeRepositoryQueryService(repos)
        app.dependency_overrides[get_repository_query_service] = lambda s=fake_service: s
        
        client = TestClient(app)
        response = client.get("/api/repositories/")
        
        # Verify expected behavior
        assert response.status_code == 200
        assert len(response.json()) == len(repos)
        
        # Clean up (FastAPI handles this automatically)
        app.dependency_overrides.clear()
    
    # Much cleaner than global state management!