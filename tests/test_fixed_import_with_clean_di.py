"""
Demonstration of how to fix failing import tests using clean FastAPI DI and fakes.

This shows the proper way to test complex endpoints that use external services.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.dependencies import get_borg_service
from app.testing.fakes import FakeBorgService
from app.models.database import Repository


class TestFixedImportWithCleanDI:
    """Demonstrate how to fix import tests using 2024 best practices."""

    def setup_method(self):
        """Clear dependency overrides before each test."""
        app.dependency_overrides.clear()

    def teardown_method(self):
        """Clean up after each test."""
        app.dependency_overrides.clear()

    def test_import_repository_success_with_fake_borg_service(self, test_db: Session):
        """Test successful import using fake Borg service (2024 best practice)."""
        
        # Arrange: Create fake Borg service that will succeed
        fake_borg = FakeBorgService(should_verify_success=True)
        
        # Use FastAPI's official dependency override system
        app.dependency_overrides[get_borg_service] = lambda: fake_borg
        
        client = TestClient(app)
        
        # Act: Import repository
        form_data = {
            "name": "test-imported-repo",
            "path": "/mnt/test-import",
            "passphrase": "test-passphrase"
        }
        
        response = client.post("/api/repositories/import", data=form_data)
        
        # Assert: Should succeed
        assert response.status_code == 200
        
        # Verify fake Borg service was called correctly
        assert len(fake_borg.verification_calls) == 1
        verify_call = fake_borg.verification_calls[0]
        assert verify_call['repo_path'] == "/mnt/test-import"
        assert verify_call['passphrase'] == "test-passphrase"
        assert verify_call['keyfile_path'] is None
        
        # Verify repository was actually created in database
        created_repo = test_db.query(Repository).filter(Repository.name == "test-imported-repo").first()
        assert created_repo is not None
        assert created_repo.path == "/mnt/test-import"

    def test_import_repository_verification_failure_clean(self, test_db: Session):
        """Test import verification failure using fake service."""
        
        # Arrange: Create fake Borg service that will fail verification
        fake_borg = FakeBorgService(should_verify_success=False)
        
        # Use FastAPI's official dependency override system  
        app.dependency_overrides[get_borg_service] = lambda: fake_borg
        
        client = TestClient(app)
        
        # Act: Try to import with service that fails verification
        form_data = {
            "name": "test-failed-import",
            "path": "/mnt/test-bad",
            "passphrase": "wrong-passphrase"
        }
        
        response = client.post("/api/repositories/import", data=form_data)
        
        # Assert: Should return 400 validation error
        assert response.status_code == 400
        assert "verify repository access" in response.json()["detail"]
        
        # Verify repository was NOT created in database (cleanup worked)
        failed_repo = test_db.query(Repository).filter(Repository.name == "test-failed-import").first()
        assert failed_repo is None

    def test_import_repository_htmx_success_clean(self, test_db: Session):
        """Test HTMX import success with proper headers."""
        
        # Arrange: Create fake Borg service that succeeds
        fake_borg = FakeBorgService(should_verify_success=True)
        app.dependency_overrides[get_borg_service] = lambda: fake_borg
        
        client = TestClient(app)
        
        # Act: Import with HTMX headers
        form_data = {
            "name": "htmx-repo",
            "path": "/mnt/htmx-test", 
            "passphrase": "htmx-pass"
        }
        
        response = client.post(
            "/api/repositories/import", 
            data=form_data,
            headers={"hx-request": "true"}
        )
        
        # Assert: Should return 200 with HTMX trigger
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "repositoryUpdate"

    def test_create_repository_success_with_fake_borg(self, test_db: Session):
        """Test repository creation using fake Borg service."""
        
        # Arrange: Create fake Borg service that succeeds initialization
        fake_borg = FakeBorgService(should_init_success=True)
        app.dependency_overrides[get_borg_service] = lambda: fake_borg
        
        client = TestClient(app)
        
        # Act: Create new repository
        repo_data = {
            "name": "test-created-repo",
            "path": "/mnt/test-create",
            "passphrase": "test-passphrase"
        }
        
        response = client.post("/api/repositories/", json=repo_data)
        
        # Assert: Should succeed
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "test-created-repo"
        assert response_data["path"] == "/mnt/test-create"
        
        # Verify fake Borg service was called for initialization
        assert len(fake_borg.initialization_calls) == 1
        init_call = fake_borg.initialization_calls[0]
        assert init_call['name'] == "test-created-repo"
        assert init_call['path'] == "/mnt/test-create"

    def test_create_repository_init_failure_clean(self, test_db: Session):
        """Test repository creation with initialization failure."""
        
        # Arrange: Create fake Borg service that fails initialization
        fake_borg = FakeBorgService(should_init_success=False)
        app.dependency_overrides[get_borg_service] = lambda: fake_borg
        
        client = TestClient(app)
        
        # Act: Try to create repository with failing Borg service
        repo_data = {
            "name": "test-failed-create", 
            "path": "/mnt/test-fail",
            "passphrase": "test-passphrase"
        }
        
        response = client.post("/api/repositories/", json=repo_data)
        
        # Assert: Should return 500 error (Borg operation failure)
        assert response.status_code == 500
        assert "Failed to initialize repository" in response.json()["detail"]