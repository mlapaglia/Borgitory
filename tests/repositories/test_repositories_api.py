"""
Tests for repositories API endpoints
"""

import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.main import app
from borgitory.api.auth import get_current_user
from borgitory.dependencies import get_repository_service
from borgitory.models.database import Repository, User
from borgitory.models.enums import EncryptionType
from borgitory.models.schemas import RepositoryCreate, RepositoryImport
from borgitory.models.repository_dtos import RepositoryOperationResult
from borgitory.services.repositories.repository_service import RepositoryService


@pytest.fixture
def mock_repo_service() -> AsyncMock:
    """Create a mock repository service."""
    return AsyncMock(spec=RepositoryService)


@pytest.fixture
async def authenticated_client(
    test_db: AsyncSession, mock_repo_service: AsyncMock
) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with authenticated user and mock service."""
    test_user = User()
    test_user.username = "test_user"
    test_user.set_password("test_password")
    test_db.add(test_user)
    await test_db.commit()
    await test_db.refresh(test_user)

    def override_get_current_user() -> User:
        return test_user

    def override_get_repository_service() -> AsyncMock:
        return mock_repo_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_repository_service] = override_get_repository_service

    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client

    from tests.conftest import clear_dependency_overrides_except_auth
    clear_dependency_overrides_except_auth()


class TestRepositoriesAPI:
    """Test class for repositories API endpoints."""

    async def test_list_repositories_empty(self, async_client: AsyncClient) -> None:
        """Test listing repositories when empty."""
        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_repositories_with_data(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """Test listing repositories with data."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "repo-1"
        repo1.path = "/tmp/repo-1"
        repo1.set_passphrase("passphrase-1")
        repo2 = Repository()
        repo2.name = "repo-2"
        repo2.path = "/tmp/repo-2"
        repo2.set_passphrase("passphrase-2")

        test_db.add_all([repo1, repo2])
        await test_db.commit()

        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "repo-1"
        assert response_data[1]["name"] == "repo-2"

    async def test_list_repositories_pagination(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        """Test listing repositories with pagination."""
        # Create multiple repositories
        for i in range(5):
            repo = Repository()
            repo.name = f"repo-{i}"
            repo.path = f"/tmp/repo-{i}"
            repo.set_passphrase(f"passphrase-{i}")
            test_db.add(repo)
        await test_db.commit()

        # Test with limit
        response = await async_client.get("/api/repositories/?skip=1&limit=2")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2

    async def test_create_repository_with_encryption_requires_passphrase(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Test that creating a repository with encryption requires a passphrase."""
        response = await authenticated_client.post(
            "/api/repositories/",
            json={
                "name": "test-repo",
                "path": "/tmp/test-repo",
                "encryption_type": "repokey",
                "passphrase": None,
                "cache_dir": None,
            },
        )

        assert response.status_code == 422
        response_data = response.json()
        assert (
            "passphrase" in response_data["detail"][0]["msg"].lower()
            or "required" in response_data["detail"][0]["msg"].lower()
        )

    async def test_create_repository_with_encryption_and_valid_passphrase(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that creating a repository with encryption and valid passphrase succeeds."""
        mock_repo_service.create_repository.return_value = RepositoryOperationResult(
            success=True,
            repository_id=1,
            repository_name="test-repo",
            message="Repository created successfully",
        )

        repo_data = RepositoryCreate(
            name="test-repo",
            path="/tmp/test-repo",
            encryption_type=EncryptionType.REPOKEY,
            passphrase="test-passphrase-12345",
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200

    async def test_create_repository_without_encryption_no_passphrase_required(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that creating a repository without encryption does not require a passphrase."""
        mock_repo_service.create_repository.return_value = RepositoryOperationResult(
            success=True, repository_id=1, repository_name="test-repo-no-encrypt"
        )

        repo_data = RepositoryCreate(
            name="test-repo-no-encrypt",
            path="/tmp/test-repo-no-encrypt",
            encryption_type=EncryptionType.NONE,
            passphrase=None,
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200

    async def test_create_repository_without_encryption_with_empty_passphrase(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that creating a repository without encryption accepts empty passphrase."""
        mock_repo_service.create_repository.return_value = RepositoryOperationResult(
            success=True, repository_id=1, repository_name="test-repo-no-encrypt"
        )

        repo_data = RepositoryCreate(
            name="test-repo-no-encrypt",
            path="/tmp/test-repo-no-encrypt",
            encryption_type=EncryptionType.NONE,
            passphrase="",
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200

    async def test_create_repository_with_short_passphrase_fails(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Test that creating a repository with a short passphrase fails validation."""
        response = await authenticated_client.post(
            "/api/repositories/",
            json={
                "name": "test-repo",
                "path": "/tmp/test-repo",
                "encryption_type": "repokey",
                "passphrase": "short",
                "cache_dir": None,
            },
        )

        assert response.status_code == 422
        response_data = response.json()
        assert "8 characters" in response_data["detail"][0]["msg"].lower()

    async def test_import_repository_with_encryption_requires_passphrase(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Test that importing a repository with encryption requires a passphrase."""
        response = await authenticated_client.post(
            "/api/repositories/import",
            json={
                "name": "imported-repo",
                "path": "/tmp/imported-repo",
                "encryption_type": "repokey",
                "passphrase": None,
                "keyfile_content": None,
                "cache_dir": None,
            },
        )

        assert response.status_code == 422
        response_data = response.json()
        assert (
            "passphrase" in response_data["detail"][0]["msg"].lower()
            or "required" in response_data["detail"][0]["msg"].lower()
        )

    async def test_import_repository_with_encryption_and_valid_passphrase(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that importing a repository with encryption and valid passphrase succeeds."""
        mock_repo_service.import_repository.return_value = RepositoryOperationResult(
            success=True,
            repository_id=1,
            repository_name="imported-repo",
            message="Repository imported successfully",
        )

        repo_data = RepositoryImport(
            name="imported-repo",
            path="/tmp/imported-repo",
            encryption_type=EncryptionType.REPOKEY,
            passphrase="test-passphrase-12345",
            keyfile_content=None,
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/import",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200

    async def test_import_repository_without_encryption_no_passphrase_required(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that importing a repository without encryption does not require a passphrase."""
        mock_repo_service.import_repository.return_value = RepositoryOperationResult(
            success=True, repository_id=1, repository_name="imported-repo-no-encrypt"
        )

        repo_data = RepositoryImport(
            name="imported-repo-no-encrypt",
            path="/tmp/imported-repo-no-encrypt",
            encryption_type=EncryptionType.NONE,
            passphrase=None,
            keyfile_content=None,
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/import",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200

    async def test_import_repository_with_keyfile_encryption(
        self, authenticated_client: AsyncClient, mock_repo_service: AsyncMock
    ) -> None:
        """Test that importing a repository with keyfile encryption works."""
        mock_repo_service.import_repository.return_value = RepositoryOperationResult(
            success=True, repository_id=1, repository_name="imported-keyfile-repo"
        )

        repo_data = RepositoryImport(
            name="imported-keyfile-repo",
            path="/tmp/imported-keyfile-repo",
            encryption_type=EncryptionType.KEYFILE,
            passphrase="test-passphrase-12345",
            keyfile_content="fake-keyfile-content",
            cache_dir=None,
        )

        response = await authenticated_client.post(
            "/api/repositories/import",
            json=repo_data.model_dump(mode="json"),
        )

        assert response.status_code == 200
