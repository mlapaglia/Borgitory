"""
Tests for repositories API endpoints
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock
from io import BytesIO

from borgitory.main import app
from borgitory.models.database import Repository, Job
from borgitory.dependencies import get_borg_service, get_volume_service
from borgitory.services.borg_service import BorgService
from borgitory.services.volumes.volume_service import VolumeService


class TestRepositoriesAPI:
    """Test class for repositories API endpoints."""

    @pytest.mark.asyncio
    async def test_list_repositories_empty(self, async_client: AsyncClient) -> None:
        """Test listing repositories when empty."""
        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_repositories_with_data(
        self, async_client: AsyncClient, test_db: Session
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
        test_db.commit()

        response = await async_client.get("/api/repositories/")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "repo-1"
        assert response_data[1]["name"] == "repo-2"

    @pytest.mark.asyncio
    async def test_list_repositories_pagination(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test listing repositories with pagination."""
        # Create multiple repositories
        for i in range(5):
            repo = Repository()
            repo.name = f"repo-{i}"
            repo.path = f"/tmp/repo-{i}"
            repo.set_passphrase(f"passphrase-{i}")
            test_db.add(repo)
        test_db.commit()

        # Test with limit
        response = await async_client.get("/api/repositories/?skip=1&limit=2")

        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2

    @pytest.mark.asyncio
    async def test_scan_repositories_success(self, async_client: AsyncClient) -> None:
        """Test successful repository scanning."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import (
            RepositoryScanResult,
            ScannedRepository,
        )

        # Create mock result that matches the DTO structure
        mock_result = RepositoryScanResult(
            success=True,
            repositories=[
                ScannedRepository(
                    name="repo1",
                    path="/path/to/repo1",
                    encryption_mode="repokey",
                    requires_keyfile=False,
                    preview="Repository preview",
                    is_existing=False,
                ),
                ScannedRepository(
                    name="repo2",
                    path="/path/to/repo2",
                    encryption_mode="keyfile",
                    requires_keyfile=True,
                    preview="Repository preview",
                    is_existing=False,
                ),
            ],
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/scan")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            mock_repo_service.scan_repositories.assert_called_once()
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test repository scanning with HTMX request."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import (
            RepositoryScanResult,
            ScannedRepository,
        )

        # Create mock result
        mock_result = RepositoryScanResult(
            success=True,
            repositories=[
                ScannedRepository(
                    name="htmx-repo",
                    path="/path/to/htmx-repo",
                    encryption_mode="repokey",
                    requires_keyfile=False,
                    preview="Repository preview",
                    is_existing=False,
                )
            ],
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                "/api/repositories/scan", headers={"hx-request": "true"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_service_error(
        self, async_client: AsyncClient
    ) -> None:
        """Test repository scanning with service error."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryScanResult

        # Create mock result with error
        mock_result = RepositoryScanResult(
            success=False, repositories=[], error_message="Scan error"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/scan")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_error(
        self, async_client: AsyncClient
    ) -> None:
        """Test repository scanning error with HTMX."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryScanResult

        # Create mock result with error
        mock_result = RepositoryScanResult(
            success=False, repositories=[], error_message="Scan error"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                "/api/repositories/scan", headers={"hx-request": "true"}
            )

            assert response.status_code == 200  # Returns error template
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_get_repositories_html_empty(self, async_client: AsyncClient) -> None:
        """Test getting repositories as HTML when empty."""
        response = await async_client.get("/api/repositories/html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_repositories_html_with_data(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting repositories as HTML with data."""
        repo = Repository()
        repo.name = "html-test-repo"
        repo.path = "/tmp/html-test"
        repo.set_passphrase("test-passphrase")
        test_db.add(repo)
        test_db.commit()

        response = await async_client.get("/api/repositories/html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_repositories_html_error_handling(
        self, async_client: AsyncClient
    ) -> None:
        """Test HTML endpoint error handling."""
        with patch("sqlalchemy.orm.Query.all", side_effect=Exception("Database error")):
            response = await async_client.get("/api/repositories/html")

            assert response.status_code == 200  # Returns error template
            content = response.text
            assert "Error loading repositories" in content

    @pytest.mark.asyncio
    async def test_list_directories_root(self, async_client: AsyncClient) -> None:
        """Test listing directories at /mnt root."""
        mock_volumes = ["/mnt/data", "/mnt/backups"]

        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes

        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service

        try:
            # Mock the secure path functions that the endpoint actually uses
            mock_directories = [
                {"name": "data", "path": "/mnt/data"},
                {"name": "backups", "path": "/mnt/backups"},
            ]

            with patch(
                "borgitory.api.repositories.user_secure_exists", return_value=True
            ), patch(
                "borgitory.api.repositories.user_secure_isdir", return_value=True
            ), patch(
                "borgitory.api.repositories.user_get_directory_listing",
                return_value=mock_directories,
            ):
                response = await async_client.get(
                    "/api/repositories/directories?path=/mnt"
                )

                assert response.status_code == 200
                response_data = response.json()
                directories = response_data["directories"]
                # All directories under /mnt should be allowed
                dir_names = [d["name"] for d in directories]
                assert "data" in dir_names
                assert "backups" in dir_names
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_valid_path(self, async_client: AsyncClient) -> None:
        """Test listing directories at valid path under /mnt."""
        mock_volumes = ["/mnt/data"]

        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes

        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service

        try:
            # Mock the secure path functions that the endpoint actually uses
            mock_directories = [
                {"name": "subdir1", "path": "/mnt/data/subdir1"},
                {"name": "subdir2", "path": "/mnt/data/subdir2"},
            ]

            with patch(
                "borgitory.api.repositories.user_secure_exists", return_value=True
            ), patch(
                "borgitory.api.repositories.user_secure_isdir", return_value=True
            ), patch(
                "borgitory.api.repositories.user_get_directory_listing",
                return_value=mock_directories,
            ):
                response = await async_client.get(
                    "/api/repositories/directories?path=/mnt/data"
                )

                assert response.status_code == 200
                response_data = response.json()
                directories = response_data["directories"]
                assert len(directories) == 2
                assert directories[0]["name"] == "subdir1"
                assert directories[1]["name"] == "subdir2"
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_nonexistent_path(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing directories for non-existent path."""
        mock_volumes = ["/data"]

        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes

        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service

        try:
            with patch("os.path.exists", return_value=False):
                response = await async_client.get(
                    "/api/repositories/directories?path=/data/nonexistent"
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_permission_denied(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing directories with permission denied."""
        mock_volumes = ["/data"]

        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes

        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service

        try:
            with patch("os.path.exists", return_value=True), patch(
                "os.path.isdir", return_value=True
            ), patch("os.listdir", side_effect=PermissionError("Permission denied")):
                response = await async_client.get(
                    "/api/repositories/directories?path=/data"
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_not_under_mounted_volume(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing directories outside mounted volumes."""
        mock_volumes = ["/data"]

        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes

        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service

        try:
            response = await async_client.get(
                "/api/repositories/directories?path=/invalid"
            )

            # With /mnt-only security model, invalid paths return empty directories
            assert response.status_code == 200
            assert response.json()["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_update_import_form_no_path(self, async_client: AsyncClient) -> None:
        """Test import form update with empty path parameter."""
        response = await async_client.get("/api/repositories/import-form-update?path=")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_update_import_form_loading_state(
        self, async_client: AsyncClient
    ) -> None:
        """Test import form update loading state."""
        response = await async_client.get(
            "/api/repositories/import-form-update?path=/test&loading=true"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_update_import_form_valid_repo(
        self, async_client: AsyncClient
    ) -> None:
        """Test import form update with valid repository."""
        mock_repos = [
            {
                "path": "/test/repo",
                "encryption_mode": "repokey",
                "requires_keyfile": False,
                "preview": "Test repository",
            }
        ]

        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.scan_for_repositories.return_value = mock_repos

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                "/api/repositories/import-form-update?path=/test/repo"
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_update_import_form_repo_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test import form update with repository not found."""
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.scan_for_repositories.return_value = []  # No repositories found

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                "/api/repositories/import-form-update?path=/missing/repo"
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_import_repository_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test successful repository import."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryOperationResult

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=123,
            repository_name="imported-repo",
            message="Repository imported successfully",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.import_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            form_data = {
                "name": "imported-repo",
                "path": "/path/to/existing/repo",
                "passphrase": "existing-passphrase",
            }

            response = await async_client.post(
                "/api/repositories/import", data=form_data
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_import_repository_htmx_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test successful repository import via HTMX."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryOperationResult

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=124,
            repository_name="htmx-imported-repo",
            message="Repository imported successfully",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.import_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            form_data = {
                "name": "htmx-imported-repo",
                "path": "/path/to/htmx/repo",
                "passphrase": "htmx-passphrase",
            }

            response = await async_client.post(
                "/api/repositories/import",
                data=form_data,
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "HX-Trigger" in response.headers
            assert response.headers["HX-Trigger"] == "repositoryUpdate"
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_import_repository_duplicate_name(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test repository import with duplicate name."""
        # Create existing repository
        existing_repo = Repository()
        existing_repo.name = "existing-import"
        existing_repo.path = "/tmp/existing"
        existing_repo.set_passphrase("existing-passphrase")
        test_db.add(existing_repo)
        test_db.commit()

        form_data = {
            "name": "existing-import",
            "path": "/path/to/different/repo",
            "passphrase": "different-passphrase",
        }

        response = await async_client.post("/api/repositories/import", data=form_data)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_import_repository_with_keyfile(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test repository import with keyfile."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryOperationResult

        keyfile_content = b"fake-keyfile-content"

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=125,
            repository_name="keyfile-repo",
            message="Repository imported successfully with keyfile",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.import_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            files = {
                "keyfile": (
                    "keyfile.key",
                    BytesIO(keyfile_content),
                    "application/octet-stream",
                )
            }
            data = {
                "name": "keyfile-repo",
                "path": "/path/to/keyfile/repo",
                "passphrase": "keyfile-passphrase",
            }

            response = await async_client.post(
                "/api/repositories/import", data=data, files=files
            )

            assert response.status_code == 200
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_import_repository_verification_failure(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test repository import with verification failure."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import RepositoryOperationResult

        # Create mock failure result
        mock_result = RepositoryOperationResult(
            success=False,
            error_message="Failed to verify repository access",
            borg_error="Failed to verify repository access",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.import_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            form_data = {
                "name": "verify-fail-repo",
                "path": "/path/to/bad/repo",
                "passphrase": "wrong-passphrase",
            }

            response = await async_client.post(
                "/api/repositories/import", data=form_data
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_get_repository_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting repository by ID."""
        repo = Repository()
        repo.name = "get-test-repo"
        repo.path = "/tmp/get-test"
        repo.set_passphrase("get-test-passphrase")
        test_db.add(repo)
        test_db.commit()

        response = await async_client.get(f"/api/repositories/{repo.id}")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "get-test-repo"
        assert response_data["id"] == repo.id

    @pytest.mark.asyncio
    async def test_get_repository_not_found(self, async_client: AsyncClient) -> None:
        """Test getting non-existent repository."""
        response = await async_client.get("/api/repositories/999")

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_repository_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test updating repository."""
        repo = Repository()
        repo.name = "update-test-repo"
        repo.path = "/tmp/update-test"
        repo.set_passphrase("old-passphrase")
        test_db.add(repo)
        test_db.commit()

        update_data = {"name": "updated-repo-name", "passphrase": "new-passphrase"}

        response = await async_client.put(
            f"/api/repositories/{repo.id}", json=update_data
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "updated-repo-name"

    @pytest.mark.asyncio
    async def test_update_repository_not_found(self, async_client: AsyncClient) -> None:
        """Test updating non-existent repository."""
        update_data = {"name": "new-name"}

        response = await async_client.put("/api/repositories/999", json=update_data)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_repository_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test deleting repository returns HTMX success response."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import DeleteRepositoryResult

        # Create mock success result
        mock_result = DeleteRepositoryResult(
            success=True, repository_name="delete-test-repo", deleted_schedules=0
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.delete(
                "/api/repositories/1", headers={"hx-request": "true"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            content = response.text
            assert "/api/shared/notification" in content
            assert "delete-test-repo" in content
            assert "deleted successfully" in content
            assert "/api/repositories/html" in content

            # Verify service was called
            mock_repo_service.delete_repository.assert_called_once()
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_delete_repository_not_found(self, async_client: AsyncClient) -> None:
        """Test deleting non-existent repository."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import DeleteRepositoryResult

        # Create mock not found result
        mock_result = DeleteRepositoryResult(
            success=False,
            repository_name="Unknown",
            error_message="Repository not found",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.delete("/api/repositories/999")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_delete_repository_with_active_jobs(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test deleting repository with active jobs."""
        repo = Repository()
        repo.name = "active-jobs-repo"
        repo.path = "/tmp/active-jobs"
        repo.set_passphrase("active-passphrase")
        test_db.add(repo)
        test_db.commit()

        # Create active job
        active_job = Job()
        active_job.repository_id = repo.id
        active_job.type = "backup"
        active_job.status = "running"
        test_db.add(active_job)
        test_db.commit()

        response = await async_client.delete(f"/api/repositories/{repo.id}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_delete_repository_schedule_cleanup(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test repository deletion HTMX response includes schedule cleanup information."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import DeleteRepositoryResult

        # Create mock success result with schedule cleanup
        mock_result = DeleteRepositoryResult(
            success=True, repository_name="schedule-prune-repo", deleted_schedules=1
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            # Make HTMX request
            response = await async_client.delete(
                "/api/repositories/1", headers={"hx-request": "true"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Verify HTMX response contains notification and repository list update
            content = response.text
            assert "/api/shared/notification" in content
            assert "schedule-prune-repo" in content
            assert "deleted successfully" in content
            assert "/api/repositories/html" in content

            # Verify service was called
            mock_repo_service.delete_repository.assert_called_once()
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_list_archives_repository_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing archives for non-existent repository."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import ArchiveListingResult

        # Create mock not found result
        mock_result = ArchiveListingResult(
            success=False,
            repository_id=999,
            repository_name="Unknown",
            archives=[],
            recent_archives=[],
            error_message="Repository not found",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.list_archives.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/999/archives")

            assert response.status_code == 200
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_get_archives_repository_selector(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting archives repository selector."""
        repo = Repository()
        repo.name = "selector-repo"
        repo.path = "/tmp/selector"
        repo.set_passphrase("selector-passphrase")
        test_db.add(repo)
        test_db.commit()

        response = await async_client.get("/api/repositories/archives/selector")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_archives_list_empty(self, async_client: AsyncClient) -> None:
        """Test getting archives list without repository ID."""
        response = await async_client.get("/api/repositories/archives/list")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_archives_list_with_repo(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting archives list with repository ID."""
        repo = Repository()
        repo.name = "list-repo"
        repo.path = "/tmp/list"
        repo.set_passphrase("list-passphrase")
        test_db.add(repo)
        test_db.commit()

        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.list_archives.return_value = []

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/archives/list?repository_id={repo.id}"
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_get_archive_contents_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting contents for non-existent repository."""
        response = await async_client.get(
            "/api/repositories/999/archives/test-archive/contents"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_extract_file_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test extracting file from archive."""
        repo = Repository()
        repo.name = "extract-repo"
        repo.path = "/tmp/extract"
        repo.set_passphrase("extract-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_file_stream = b"file content"

        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.extract_file_stream.return_value = mock_file_stream

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/extract?file=test.txt"
            )

            assert response.status_code == 200
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self, async_client: AsyncClient) -> None:
        """Test extracting file from non-existent repository."""
        response = await async_client.get(
            "/api/repositories/999/archives/test-archive/extract?file=test.txt"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_stats_selector(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting repository selector for statistics."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "stats-repo-1"
        repo1.path = "/tmp/stats1"
        repo1.set_passphrase("pass1")
        repo2 = Repository()
        repo2.name = "stats-repo-2"
        repo2.path = "/tmp/stats2"
        repo2.set_passphrase("pass2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        response = await async_client.get("/api/repositories/stats/selector")

        assert response.status_code == 200
        # Verify HTML response contains repository options
        content = response.text
        assert "stats-repo-1" in content
        assert "stats-repo-2" in content

    @pytest.mark.asyncio
    async def test_get_stats_loading(self, async_client: AsyncClient) -> None:
        """Test getting loading state for statistics."""
        response = await async_client.get(
            "/api/repositories/stats/loading?repository_id=1"
        )

        assert response.status_code == 200
        # Verify HTML response contains loading template
        content = response.text
        assert "repository_id" in content or "loading" in content.lower()

    @pytest.mark.asyncio
    async def test_get_stats_loading_no_repository(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting loading state without repository ID."""
        response = await async_client.get("/api/repositories/stats/loading")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_repository_statistics_direct(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test the direct repository statistics endpoint."""
        from borgitory.dependencies import get_repository_stats_service
        from borgitory.services.repositories.repository_stats_service import (
            RepositoryStatsService,
        )

        # Create test repository
        repo = Repository()
        repo.name = "direct-stats-repo"
        repo.path = "/tmp/direct-stats"
        repo.set_passphrase("direct-pass")
        test_db.add(repo)
        test_db.commit()

        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.return_value = {
            "repository_path": "/tmp/direct-stats",
            "total_archives": 3,
            "archive_stats": [],
            "size_over_time": {
                "labels": ["2024-01-01"],
                "datasets": [
                    {
                        "label": "Original Size",
                        "data": [100.0],
                        "borderColor": "rgb(59, 130, 246)",
                        "backgroundColor": "rgba(59, 130, 246, 0.1)",
                        "fill": False,
                    }
                ],
            },
            "dedup_compression_stats": {
                "labels": ["2024-01-01"],
                "datasets": [
                    {
                        "label": "Compression Ratio %",
                        "data": [20.0],
                        "borderColor": "rgb(139, 92, 246)",
                        "backgroundColor": "rgba(139, 92, 246, 0.1)",
                        "fill": False,
                        "yAxisID": "y",
                    }
                ],
            },
            "file_type_stats": {
                "count_chart": {
                    "labels": ["text"],
                    "datasets": [
                        {
                            "label": ".txt files",
                            "data": [100.0],
                            "borderColor": "rgb(59, 130, 246)",
                            "backgroundColor": "rgba(59, 130, 246, 0.1)",
                            "fill": False,
                        }
                    ],
                },
                "size_chart": {
                    "labels": ["text"],
                    "datasets": [
                        {
                            "label": ".txt size (MB)",
                            "data": [1000.0],
                            "borderColor": "rgb(59, 130, 246)",
                            "backgroundColor": "rgba(59, 130, 246, 0.1)",
                            "fill": False,
                        }
                    ],
                },
            },
            "summary": {
                "total_archives": 3,
                "latest_archive_date": "2024-01-01",
                "total_original_size_gb": 5.0,
                "total_compressed_size_gb": 4.0,
                "total_deduplicated_size_gb": 3.0,
                "overall_compression_ratio": 20.0,
                "overall_deduplication_ratio": 25.0,
                "space_saved_gb": 2.0,
                "average_archive_size_gb": 1.67,
            },
        }

        app.dependency_overrides[get_repository_stats_service] = (
            lambda command_executor=None: mock_stats_service
        )

        try:
            response = await async_client.get(f"/api/repositories/{repo.id}/stats")

            assert response.status_code == 200
            response_data = response.json()

            # Verify the response structure matches the stats service return
            assert response_data["repository_path"] == "/tmp/direct-stats"
            assert response_data["total_archives"] == 3
            assert "archive_stats" in response_data
            assert "size_over_time" in response_data
            assert "dedup_compression_stats" in response_data
            assert "count_chart" in response_data["file_type_stats"]
            assert "size_chart" in response_data["file_type_stats"]
            assert "summary" in response_data
            assert response_data["summary"]["total_archives"] == 3

        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_get_repository_statistics_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test repository statistics endpoint with non-existent repository."""
        from borgitory.dependencies import get_repository_stats_service
        from borgitory.services.repositories.repository_stats_service import (
            RepositoryStatsService,
        )

        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        app.dependency_overrides[get_repository_stats_service] = (
            lambda: mock_stats_service
        )

        try:
            response = await async_client.get("/api/repositories/999/stats")

            assert response.status_code == 404

        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_directories_autocomplete_htmx_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that autocomplete endpoint returns proper HTMX HTML response."""
        from borgitory.api.auth import get_current_user
        from borgitory.models.database import User

        # Create a test user and mock authentication
        test_user = User()
        test_user.username = "testuser"
        test_user.set_password("testpass")
        test_db.add(test_user)
        test_db.commit()
        test_db.refresh(test_user)

        def override_get_current_user() -> User:
            return test_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        # Mock the secure path functions to return some test data
        from borgitory.api import repositories

        original_exists = repositories.user_secure_exists
        original_isdir = repositories.user_secure_isdir
        original_listing = repositories.user_get_directory_listing

        repositories.user_secure_exists = lambda path: True
        repositories.user_secure_isdir = lambda path: True
        repositories.user_get_directory_listing = lambda path, include_files=True: [
            {"name": "data", "path": "/mnt/data"},
            {"name": "backup", "path": "/mnt/backup"},
        ]

        try:
            # Test basic HTMX response
            response = await async_client.get(
                "/api/repositories/directories/autocomplete?path=data"
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check that response contains expected HTML structure
            content = response.text
            assert "data" in content

            # Test with HTMX target header
            response = await async_client.get(
                "/api/repositories/directories/autocomplete?path=data",
                headers={"hx-target-input": "test-input-id"},
            )

            assert response.status_code == 200
            assert "test-input-id" in response.text

        finally:
            # Restore original functions
            repositories.user_secure_exists = original_exists
            repositories.user_secure_isdir = original_isdir
            repositories.user_get_directory_listing = original_listing
