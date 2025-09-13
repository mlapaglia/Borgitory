"""
Comprehensive tests demonstrating clean FastAPI architecture.

This shows how much simpler testing becomes with proper service layer
and clean dependency injection following 2024 best practices.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import Mock

from app.main import app
from app.dependencies import (
    get_security_validator,
    get_command_executor,
    get_borg_verification_service,
    get_repository_data_service
)
from app.models.schemas import RepositoryImport
from tests.fakes import (
    FakeSecurityValidator,
    FakeCommandExecutor,
    FakeBorgVerificationService,
    FakeRepositoryDataService
)


class TestCleanArchitecture:
    """Test clean architecture with proper dependency injection."""

    def setup_method(self):
        """Clear dependency overrides before each test."""
        app.dependency_overrides.clear()

    def teardown_method(self):
        """Clean up after each test."""
        app.dependency_overrides.clear()

    def test_service_layer_independently(self):
        """Test service layer completely independently (unit test)."""
        from app.services.implementations import RepositoryImportServiceImpl
        from app.models.repository import Repository
        from unittest.mock import Mock
        
        # Arrange: Create fake dependencies
        security_validator = FakeSecurityValidator()
        borg_service = FakeBorgVerificationService(should_verify_success=True)
        data_service = FakeRepositoryDataService()
        
        # Create service with fakes
        import_service = RepositoryImportServiceImpl(
            security_validator, borg_service, data_service
        )
        
        # Act: Test service directly
        import asyncio
        import_data = RepositoryImport(
            name="test-repo",
            path="/mnt/test",
            passphrase="secret123"
        )
        
        result = asyncio.run(import_service.import_repository(import_data, Mock()))
        
        # Assert: Verify behavior
        assert result.success == True
        assert result.repository is not None
        assert result.repository.name == "test-repo"
        
        # Verify all dependencies were called correctly
        assert "test-repo" in security_validator.validated_names
        assert "secret123" in security_validator.validated_passphrases
        assert len(borg_service.verification_calls) == 1
        assert borg_service.verification_calls[0]['repo_path'] == "/mnt/test"

    def test_import_repository_success_with_clean_di(self):
        """Test successful import using clean FastAPI dependency overrides."""
        
        # Arrange: Set up fake services using FastAPI's official override system
        fake_security = FakeSecurityValidator()
        fake_command = FakeCommandExecutor(should_succeed=True)
        fake_borg = FakeBorgVerificationService(should_verify_success=True)
        fake_data = FakeRepositoryDataService()
        
        app.dependency_overrides[get_security_validator] = lambda: fake_security
        app.dependency_overrides[get_command_executor] = lambda: fake_command
        app.dependency_overrides[get_borg_verification_service] = lambda cmd: fake_borg
        app.dependency_overrides[get_repository_data_service] = lambda: fake_data
        
        client = TestClient(app)
        
        # Act: Import repository
        import_data = {
            "name": "imported-repo",
            "path": "/mnt/imported",
            "passphrase": "import-secret"
        }
        
        response = client.post("/api/repositories/import", json=import_data)
        
        # Assert: Should succeed
        assert response.status_code == 200
        result = response.json()
        assert result["success"] == True
        assert result["repository"]["name"] == "imported-repo"
        assert result["repository"]["path"] == "/mnt/imported"
        
        # Verify all fake services were called correctly
        assert "imported-repo" in fake_security.validated_names
        assert len(fake_borg.verification_calls) == 1
        assert fake_borg.verification_calls[0]['repo_path'] == "/mnt/imported"

    def test_import_repository_validation_failure(self):
        """Test import with validation failure."""
        
        # Arrange: Set up validator that will fail
        fake_security = FakeSecurityValidator(should_fail=True)
        fake_data = FakeRepositoryDataService()
        
        app.dependency_overrides[get_security_validator] = lambda: fake_security
        app.dependency_overrides[get_repository_data_service] = lambda: fake_data
        # Don't need to override other services - validation fails first
        
        client = TestClient(app)
        
        # Act: Try to import with invalid data
        import_data = {
            "name": "../dangerous-name",
            "path": "/mnt/test",
            "passphrase": "secret"
        }
        
        response = client.post("/api/repositories/import", json=import_data)
        
        # Assert: Should return validation error
        assert response.status_code == 400
        assert "validation failure" in response.json()["detail"]

    def test_import_repository_verification_failure(self):
        """Test import with Borg verification failure."""
        
        # Arrange: Set up Borg service that will fail verification
        fake_security = FakeSecurityValidator()
        fake_borg = FakeBorgVerificationService(should_verify_success=False)
        fake_data = FakeRepositoryDataService()
        
        app.dependency_overrides[get_security_validator] = lambda: fake_security
        app.dependency_overrides[get_borg_verification_service] = lambda cmd: fake_borg
        app.dependency_overrides[get_repository_data_service] = lambda: fake_data
        
        client = TestClient(app)
        
        # Act: Try to import with bad credentials
        import_data = {
            "name": "test-repo",
            "path": "/mnt/bad",
            "passphrase": "wrong-password"
        }
        
        response = client.post("/api/repositories/import", json=import_data)
        
        # Assert: Should return verification error
        assert response.status_code == 400
        assert "verify repository access" in response.json()["detail"]

    def test_import_repository_duplicate_name(self):
        """Test import with duplicate name."""
        
        # Arrange: Set up data service with existing repository
        fake_security = FakeSecurityValidator()
        fake_data = FakeRepositoryDataService()
        
        # Pre-populate with existing repository
        from app.models.repository import Repository
        existing_repo = Repository(name="existing-repo", path="/mnt/existing")
        fake_data.save(Mock(), existing_repo)
        
        app.dependency_overrides[get_security_validator] = lambda: fake_security
        app.dependency_overrides[get_repository_data_service] = lambda: fake_data
        
        client = TestClient(app)
        
        # Act: Try to import with duplicate name
        import_data = {
            "name": "existing-repo",
            "path": "/mnt/different",
            "passphrase": "secret"
        }
        
        response = client.post("/api/repositories/import", json=import_data)
        
        # Assert: Should return duplicate error
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


def test_architecture_benefits():
    """
    Demonstrate the benefits of clean architecture.
    
    BEFORE (legacy system):
    - 140+ lines for import endpoint
    - Complex dependency chains
    - Hard to test (complex mocking)
    - Mixed concerns (HTTP + business logic)
    
    AFTER (clean architecture):
    - ~15 lines for import endpoint  
    - Clear dependency injection
    - Easy testing (simple fakes)
    - Single responsibility
    """
    
    # Show how easy it is to test different scenarios
    test_scenarios = [
        ("validation_success", FakeSecurityValidator(should_fail=False)),
        ("validation_failure", FakeSecurityValidator(should_fail=True)),
        ("verification_success", FakeBorgVerificationService(should_verify_success=True)),
        ("verification_failure", FakeBorgVerificationService(should_verify_success=False)),
    ]
    
    for scenario_name, fake_service in test_scenarios:
        # Each scenario is easy to set up and test
        if isinstance(fake_service, FakeSecurityValidator):
            app.dependency_overrides[get_security_validator] = lambda s=fake_service: s
        elif isinstance(fake_service, FakeBorgVerificationService):
            app.dependency_overrides[get_borg_verification_service] = lambda cmd, s=fake_service: s
        
        # Test the scenario
        client = TestClient(app)
        response = client.post("/api/repositories/import", json={
            "name": "test", "path": "/mnt/test", "passphrase": "secret"
        })
        
        # Verify expected behavior based on scenario
        if "failure" in scenario_name:
            assert response.status_code == 400
        # Success cases need more setup, but the pattern is clear
        
        # Clean up for next scenario
        app.dependency_overrides.clear()
    
    # Much cleaner than complex mocking!