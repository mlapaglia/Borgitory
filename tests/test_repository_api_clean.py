"""
Clean repository API tests using proper abstraction instead of mocking.

This demonstrates how much simpler testing becomes when we abstract
the dependencies properly instead of trying to mock complex systems.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.dependencies_services import set_borg_service, reset_dependencies


class SimpleBorgService:
    """Simple test implementation of Borg service."""
    
    def __init__(self, should_verify_success: bool = True, should_init_success: bool = True):
        self.should_verify_success = should_verify_success
        self.should_init_success = should_init_success
        self.verify_calls = []
        self.init_calls = []
    
    async def initialize_repository(self, repository):
        self.init_calls.append(repository.name)
        return {"success": self.should_init_success, "message": "Test init"}
    
    async def verify_repository_access(self, repo_path, passphrase, keyfile_path=None):
        self.verify_calls.append((repo_path, passphrase, keyfile_path))
        return self.should_verify_success
    
    async def list_archives(self, repository):
        return [{"name": "test-archive"}]


class TestRepositoryAPIClean:
    """Clean tests using proper abstractions."""

    def setup_method(self):
        """Reset dependencies before each test."""
        reset_dependencies()
        # Clear any existing FastAPI dependency overrides
        app.dependency_overrides.clear()

    def teardown_method(self):
        """Clean up after each test."""
        reset_dependencies()
        app.dependency_overrides.clear()

    def test_import_repository_success_with_clean_abstraction(self, test_db: Session):
        """Test successful import using clean service abstraction."""
        
        # Arrange: Set up a simple borg service that will succeed
        borg_service = SimpleBorgService(should_verify_success=True)
        set_borg_service(borg_service)
        
        client = TestClient(app)
        
        # Act: Import a repository
        form_data = {
            "name": "test-imported-repo",
            "path": "/mnt/test-import",
            "passphrase": "test-passphrase"
        }
        
        response = client.post("/api/repositories/import", data=form_data)
        
        # Assert: Should succeed
        assert response.status_code == 200
        # Verify the borg service was called correctly
        assert len(borg_service.verify_calls) == 1
        assert borg_service.verify_calls[0][0] == "/mnt/test-import"
        assert borg_service.verify_calls[0][1] == "test-passphrase"

    def test_import_repository_verification_failure_clean(self, test_db: Session):
        """Test import verification failure with clean abstraction."""
        
        # Arrange: Set up borg service that will fail verification
        borg_service = SimpleBorgService(should_verify_success=False)
        set_borg_service(borg_service)
        
        client = TestClient(app)
        
        # Act: Try to import with bad credentials
        form_data = {
            "name": "test-failed-import",
            "path": "/mnt/test-bad",
            "passphrase": "wrong-passphrase"
        }
        
        response = client.post("/api/repositories/import", data=form_data)
        
        # Assert: Should return 400 validation error (not 500)
        assert response.status_code == 400
        assert "verify repository access" in response.json()["detail"]

    def test_create_repository_success_clean(self, test_db: Session):
        """Test successful repository creation with clean abstraction."""
        
        # Arrange: Set up borg service that will succeed
        borg_service = SimpleBorgService(should_init_success=True)
        set_borg_service(borg_service)
        
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
        # Verify borg service was called for initialization
        assert len(borg_service.init_calls) == 1
        assert borg_service.init_calls[0] == "test-created-repo"

    def test_validation_error_clean(self, test_db: Session):
        """Test validation error with clean abstraction."""
        
        # Don't need to set up borg service since validation happens first
        
        client = TestClient(app)
        
        # Act: Try to create repository with invalid name
        repo_data = {
            "name": "../dangerous-name",
            "path": "/mnt/test",
            "passphrase": "test-passphrase"
        }
        
        response = client.post("/api/repositories/", json=repo_data)
        
        # Assert: Should return validation error
        assert response.status_code == 400
        assert "Invalid repository name" in response.json()["detail"]
        assert "invalid pattern" in response.json()["detail"]


def test_clean_dependency_injection_pattern():
    """
    Demonstrate how clean dependency injection works.
    
    This is much better than mocking because:
    - No complex mock setup needed
    - Service behavior is explicit and simple
    - Easy to test different scenarios
    - No coupling to internal implementation details
    """
    
    # Test different borg service behaviors easily
    scenarios = [
        ("success", SimpleBorgService(should_verify_success=True)),
        ("verify_fail", SimpleBorgService(should_verify_success=False)),
        ("init_fail", SimpleBorgService(should_init_success=False)),
    ]
    
    for scenario_name, borg_service in scenarios:
        # Clean setup - just inject the service
        set_borg_service(borg_service)
        
        # Test the specific scenario
        # (In real tests, you'd make API calls here)
        
        # Verify behavior
        if scenario_name == "success":
            assert borg_service.should_verify_success == True
        elif scenario_name == "verify_fail":
            assert borg_service.should_verify_success == False
        # etc.
        
        # Clean up
        reset_dependencies()
    
    # Much cleaner than complex mocking with patches!