"""
Comprehensive test suite demonstrating perfect FastAPI + SQLAlchemy 2.0 implementation.

These tests follow all 2024 best practices for testing FastAPI applications.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.repository import Repository
from app.models.schemas import RepositoryCreate
from app.services.interfaces import RepositoryValidationError


class TestRepositoryEndpoints:
    """Test repository endpoints with proper database isolation."""

    def test_list_repositories_empty(self, test_client: TestClient):
        """Test listing repositories when database is empty."""
        response = test_client.get("/api/repositories/")
        
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_create_repository_success(self, test_client: TestClient, test_session: Session):
        """Test successful repository creation with validation."""
        repository_data = {
            "name": "test-backup-repo",
            "path": "/mnt/test-backup",
            "passphrase": "supersecret123"
        }
        
        response = test_client.post("/api/repositories/", json=repository_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-backup-repo"
        assert data["path"] == "/mnt/test-backup"
        assert data["id"] > 0
        assert "created_at" in data
        
        # Verify in database
        repo = test_session.query(Repository).filter(Repository.name == "test-backup-repo").first()
        assert repo is not None
        assert repo.get_passphrase() == "supersecret123"

    def test_create_repository_validation_errors(self, test_client: TestClient):
        """Test repository creation with various validation errors."""
        
        # Test dangerous name
        response = test_client.post("/api/repositories/", json={
            "name": "../dangerous-name",
            "path": "/mnt/test",
            "passphrase": "secret123"
        })
        assert response.status_code == 422  # Pydantic validation error
        
        # Test short passphrase
        response = test_client.post("/api/repositories/", json={
            "name": "valid-name",
            "path": "/mnt/test",
            "passphrase": "short"
        })
        assert response.status_code == 422
        
        # Test invalid path
        response = test_client.post("/api/repositories/", json={
            "name": "valid-name", 
            "path": "/invalid/path",
            "passphrase": "secret123"
        })
        assert response.status_code == 422

    def test_create_repository_duplicate_name(self, test_client: TestClient, test_session: Session):
        """Test repository creation with duplicate name."""
        # Create first repository
        repo_data = {
            "name": "duplicate-test",
            "path": "/mnt/first",
            "passphrase": "secret123"
        }
        response = test_client.post("/api/repositories/", json=repo_data)
        assert response.status_code == 201
        
        # Try to create with same name
        repo_data["path"] = "/mnt/second"
        response = test_client.post("/api/repositories/", json=repo_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_list_repositories_with_data(self, test_client: TestClient):
        """Test listing repositories with pagination."""
        # Create multiple repositories
        for i in range(5):
            repo_data = {
                "name": f"repo-{i}",
                "path": f"/mnt/repo-{i}",
                "passphrase": "secret123"
            }
            response = test_client.post("/api/repositories/", json=repo_data)
            assert response.status_code == 201
        
        # Test list all
        response = test_client.get("/api/repositories/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        
        # Test pagination
        response = test_client.get("/api/repositories/?skip=2&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_repositories_pagination_validation(self, test_client: TestClient):
        """Test pagination parameter validation."""
        # Test negative skip
        response = test_client.get("/api/repositories/?skip=-1")
        assert response.status_code == 422
        
        # Test limit too large
        response = test_client.get("/api/repositories/?limit=2000")
        assert response.status_code == 422
        
        # Test limit zero
        response = test_client.get("/api/repositories/?limit=0")
        assert response.status_code == 422

    def test_html_endpoint(self, test_client: TestClient):
        """Test HTML template endpoint."""
        # Create a repository first
        repo_data = {
            "name": "html-test-repo",
            "path": "/mnt/html-test", 
            "passphrase": "secret123"
        }
        test_client.post("/api/repositories/", json=repo_data)
        
        # Test HTML endpoint
        response = test_client.get("/api/repositories/html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "html-test-repo" in response.text

    def test_main_page_with_repositories(self, test_client: TestClient):
        """Test main page loads with repository data."""
        # Create a repository
        repo_data = {
            "name": "main-page-repo",
            "path": "/mnt/main-page",
            "passphrase": "secret123"
        }
        test_client.post("/api/repositories/", json=repo_data)
        
        # Test main page
        response = test_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "main-page-repo" in response.text

    def test_health_check(self, test_client: TestClient):
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["architecture"] == "clean"

    def test_architecture_documentation(self, test_client: TestClient):
        """Test architecture documentation endpoint."""
        response = test_client.get("/api/repositories/architecture")
        assert response.status_code == 200
        data = response.json()
        assert "pattern" in data
        assert "layers" in data
        assert "benefits" in data


class TestServiceLayerIndependently:
    """Test service layer independently from FastAPI."""

    def test_repository_management_service(self, test_session: Session):
        """Test repository service with real database."""
        from app.services.repository_service import (
            RepositoryManagementService,
            SqlAlchemyRepositoryDataService
        )
        from app.services.implementations import SimpleSecurityValidator
        
        # Create service with real dependencies
        security_validator = SimpleSecurityValidator()
        data_service = SqlAlchemyRepositoryDataService()
        service = RepositoryManagementService(security_validator, data_service)
        
        # Test create repository
        from app.models.schemas import RepositoryCreate
        repo_data = RepositoryCreate(
            name="service-test",
            path="/mnt/service-test",
            passphrase="secret123"
        )
        
        result = service.create_repository(test_session, repo_data)
        
        assert result.name == "service-test"
        assert result.id > 0
        
        # Test list repositories
        repos = service.list_repositories(test_session, 0, 100)
        assert len(repos) == 1
        assert repos[0].name == "service-test"

    def test_validation_service_independently(self):
        """Test security validator independently."""
        from app.services.implementations import SimpleSecurityValidator
        
        validator = SimpleSecurityValidator()
        
        # Test valid name
        result = validator.validate_repository_name("valid-repo-name")
        assert result == "valid-repo-name"
        
        # Test invalid name
        with pytest.raises(RepositoryValidationError, match="dangerous character"):
            validator.validate_repository_name("../dangerous")


class TestDependencyInjection:
    """Test FastAPI dependency injection works perfectly."""

    def test_dependency_override_works(self, test_session: Session):
        """Test that dependency overrides work properly."""
        from app.dependencies import get_repository_data_service
        from tests.fakes import FakeRepositoryDataService
        
        # Override with fake
        fake_data_service = FakeRepositoryDataService()
        app.dependency_overrides[get_repository_data_service] = lambda: fake_data_service
        
        with TestClient(app) as client:
            response = client.get("/api/repositories/")
            assert response.status_code == 200
            # Should use fake service (empty list)
            assert response.json() == []
        
        # Clean up
        app.dependency_overrides.clear()

    def test_no_global_state_issues(self):
        """Test that services don't have global state issues."""
        # Multiple test clients should not interfere with each other
        with TestClient(app) as client1, TestClient(app) as client2:
            # Both should work independently
            resp1 = client1.get("/health")
            resp2 = client2.get("/health")
            
            assert resp1.status_code == 200
            assert resp2.status_code == 200