"""
Tests for repositories API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock
from io import BytesIO

from app.main import app
from app.models.database import Repository, Job
from app.dependencies import get_borg_service, get_volume_service
from app.services.borg_service import BorgService
from app.services.volumes.volume_service import VolumeService


class TestRepositoriesAPI:
    """Test class for repositories API endpoints."""



    @pytest.mark.asyncio
    async def test_list_repositories_empty(self, async_client: AsyncClient):
        """Test listing repositories when empty."""
        response = await async_client.get("/api/repositories/")
        
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_repositories_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test listing repositories with data."""
        # Create test repositories
        repo1 = Repository(name="repo-1", path="/tmp/repo-1")
        repo1.set_passphrase("passphrase-1")
        repo2 = Repository(name="repo-2", path="/tmp/repo-2")
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
    async def test_list_repositories_pagination(self, async_client: AsyncClient, test_db: Session):
        """Test listing repositories with pagination."""
        # Create multiple repositories
        for i in range(5):
            repo = Repository(name=f"repo-{i}", path=f"/tmp/repo-{i}")
            repo.set_passphrase(f"passphrase-{i}")
            test_db.add(repo)
        test_db.commit()
        
        # Test with limit
        response = await async_client.get("/api/repositories/?skip=1&limit=2")
        
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2

    @pytest.mark.asyncio
    async def test_scan_repositories_success(self, async_client: AsyncClient):
        """Test successful repository scanning."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryScanResult, ScannedRepository

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
                    is_existing=False
                ),
                ScannedRepository(
                    name="repo2",
                    path="/path/to/repo2",
                    encryption_mode="keyfile",
                    requires_keyfile=True,
                    preview="Repository preview",
                    is_existing=False
                )
            ]
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/scan")

            assert response.status_code == 200
            response_data = response.json()
            assert "repositories" in response_data
            assert len(response_data["repositories"]) == 2
            mock_repo_service.scan_repositories.assert_called_once()
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_response(self, async_client: AsyncClient):
        """Test repository scanning with HTMX request."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryScanResult, ScannedRepository

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
                    is_existing=False
                )
            ]
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                "/api/repositories/scan",
                headers={"hx-request": "true"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_service_error(self, async_client: AsyncClient):
        """Test repository scanning with service error."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryScanResult

        # Create mock result with error
        mock_result = RepositoryScanResult(
            success=False,
            repositories=[],
            error_message="Scan error"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/scan")

            assert response.status_code == 500
            assert "Failed to scan repositories" in response.json()["detail"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_error(self, async_client: AsyncClient):
        """Test repository scanning error with HTMX."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryScanResult

        # Create mock result with error
        mock_result = RepositoryScanResult(
            success=False,
            repositories=[],
            error_message="Scan error"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.scan_repositories.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                "/api/repositories/scan",
                headers={"hx-request": "true"}
            )

            assert response.status_code == 200  # Returns error template
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_get_repositories_html_empty(self, async_client: AsyncClient):
        """Test getting repositories as HTML when empty."""
        response = await async_client.get("/api/repositories/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_repositories_html_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test getting repositories as HTML with data."""
        repo = Repository(name="html-test-repo", path="/tmp/html-test")
        repo.set_passphrase("test-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        response = await async_client.get("/api/repositories/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_repositories_html_error_handling(self, async_client: AsyncClient):
        """Test HTML endpoint error handling."""
        with patch('sqlalchemy.orm.Query.all', side_effect=Exception("Database error")):
            response = await async_client.get("/api/repositories/html")
            
            assert response.status_code == 200  # Returns error template
            content = response.text
            assert "Error loading repositories" in content

    @pytest.mark.asyncio
    async def test_list_directories_root(self, async_client: AsyncClient):
        """Test listing directories at /mnt root."""
        mock_volumes = ["/mnt/data", "/mnt/backups"]
        
        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes
        
        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service
        
        try:
            from unittest.mock import Mock
            
            # Mock pathlib.Path methods
            mock_data = Mock()
            mock_data.name = "data"
            mock_data.is_dir.return_value = True
            mock_data.is_file.return_value = False
            mock_data.__str__ = Mock(return_value="/mnt/data")
            
            mock_backups = Mock()
            mock_backups.name = "backups"
            mock_backups.is_dir.return_value = True
            mock_backups.is_file.return_value = False
            mock_backups.__str__ = Mock(return_value="/mnt/backups")
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir', return_value=[mock_data, mock_backups]):
                
                response = await async_client.get("/api/repositories/directories?path=/mnt")
                
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
    async def test_list_directories_valid_path(self, async_client: AsyncClient):
        """Test listing directories at valid path under /mnt."""
        mock_volumes = ["/mnt/data"]
        
        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes
        
        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service
        
        try:
            from unittest.mock import Mock
            
            # Mock pathlib.Path methods
            mock_subdir1 = Mock()
            mock_subdir1.name = "subdir1"
            mock_subdir1.is_dir.return_value = True
            mock_subdir1.is_file.return_value = False
            mock_subdir1.__str__ = Mock(return_value="/mnt/data/subdir1")
            
            mock_subdir2 = Mock()
            mock_subdir2.name = "subdir2"
            mock_subdir2.is_dir.return_value = True
            mock_subdir2.is_file.return_value = False
            mock_subdir2.__str__ = Mock(return_value="/mnt/data/subdir2")
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.is_dir', return_value=True), \
                 patch('pathlib.Path.iterdir', return_value=[mock_subdir1, mock_subdir2]):
                
                response = await async_client.get("/api/repositories/directories?path=/mnt/data")
                
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
    async def test_list_directories_nonexistent_path(self, async_client: AsyncClient):
        """Test listing directories for non-existent path."""
        mock_volumes = ["/data"]
        
        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes
        
        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service
        
        try:
            with patch('os.path.exists', return_value=False):
                response = await async_client.get("/api/repositories/directories?path=/data/nonexistent")
                
                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_permission_denied(self, async_client: AsyncClient):
        """Test listing directories with permission denied."""
        mock_volumes = ["/data"]
        
        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes
        
        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service
        
        try:
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.isdir', return_value=True), \
                 patch('os.listdir', side_effect=PermissionError("Permission denied")):
                
                response = await async_client.get("/api/repositories/directories?path=/data")
                
                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_list_directories_not_under_mounted_volume(self, async_client: AsyncClient):
        """Test listing directories outside mounted volumes."""
        mock_volumes = ["/data"]
        
        # Create mock service
        mock_volume_service = AsyncMock(spec=VolumeService)
        mock_volume_service.get_mounted_volumes.return_value = mock_volumes
        
        # Override dependency injection
        app.dependency_overrides[get_volume_service] = lambda: mock_volume_service
        
        try:
            response = await async_client.get("/api/repositories/directories?path=/invalid")
            
            # With /mnt-only security model, invalid paths return empty directories
            assert response.status_code == 200
            assert response.json()["directories"] == []
        finally:
            # Clean up
            if get_volume_service in app.dependency_overrides:
                del app.dependency_overrides[get_volume_service]

    @pytest.mark.asyncio
    async def test_update_import_form_no_path(self, async_client: AsyncClient):
        """Test import form update with no path."""
        response = await async_client.get("/api/repositories/import-form-update")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_update_import_form_loading_state(self, async_client: AsyncClient):
        """Test import form update loading state."""
        response = await async_client.get("/api/repositories/import-form-update?path=/test&loading=true")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_update_import_form_valid_repo(self, async_client: AsyncClient):
        """Test import form update with valid repository."""
        mock_repos = [
            {
                "path": "/test/repo",
                "encryption_mode": "repokey",
                "requires_keyfile": False,
                "preview": "Test repository"
            }
        ]
        
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.scan_for_repositories.return_value = mock_repos
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get("/api/repositories/import-form-update?path=/test/repo")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_update_import_form_repo_not_found(self, async_client: AsyncClient):
        """Test import form update with repository not found."""
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.scan_for_repositories.return_value = []  # No repositories found
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get("/api/repositories/import-form-update?path=/missing/repo")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_import_repository_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful repository import."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryOperationResult

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=123,
            repository_name="imported-repo",
            message="Repository imported successfully"
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
                "passphrase": "existing-passphrase"
            }

            response = await async_client.post("/api/repositories/import", data=form_data)

            assert response.status_code == 200
            response_data = response.json()
            assert response_data["repository_name"] == "imported-repo"
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_import_repository_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful repository import via HTMX."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryOperationResult

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=124,
            repository_name="htmx-imported-repo",
            message="Repository imported successfully"
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
                "passphrase": "htmx-passphrase"
            }

            response = await async_client.post(
                "/api/repositories/import",
                data=form_data,
                headers={"hx-request": "true"}
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
    async def test_import_repository_duplicate_name(self, async_client: AsyncClient, test_db: Session):
        """Test repository import with duplicate name."""
        # Create existing repository
        existing_repo = Repository(name="existing-import", path="/tmp/existing")
        existing_repo.set_passphrase("existing-passphrase")
        test_db.add(existing_repo)
        test_db.commit()
        
        form_data = {
            "name": "existing-import",
            "path": "/path/to/different/repo",
            "passphrase": "different-passphrase"
        }
        
        response = await async_client.post("/api/repositories/import", data=form_data)
        
        assert response.status_code == 400
        assert "Repository with this name already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_repository_with_keyfile(self, async_client: AsyncClient, test_db: Session):
        """Test repository import with keyfile."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryOperationResult

        keyfile_content = b"fake-keyfile-content"

        # Create mock success result
        mock_result = RepositoryOperationResult(
            success=True,
            repository_id=125,
            repository_name="keyfile-repo",
            message="Repository imported successfully with keyfile"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.import_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            files = {"keyfile": ("keyfile.key", BytesIO(keyfile_content), "application/octet-stream")}
            data = {
                "name": "keyfile-repo",
                "path": "/path/to/keyfile/repo",
                "passphrase": "keyfile-passphrase"
            }

            response = await async_client.post("/api/repositories/import", data=data, files=files)

            assert response.status_code == 200
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_import_repository_verification_failure(self, async_client: AsyncClient, test_db: Session):
        """Test repository import with verification failure."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import RepositoryOperationResult

        # Create mock failure result
        mock_result = RepositoryOperationResult(
            success=False,
            error_message="Failed to verify repository access",
            borg_error="Failed to verify repository access"
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
                "passphrase": "wrong-passphrase"
            }

            response = await async_client.post("/api/repositories/import", data=form_data)

            assert response.status_code == 400
            assert "Failed to verify repository access" in response.json()["detail"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_get_repository_success(self, async_client: AsyncClient, test_db: Session):
        """Test getting repository by ID."""
        repo = Repository(name="get-test-repo", path="/tmp/get-test")
        repo.set_passphrase("get-test-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        response = await async_client.get(f"/api/repositories/{repo.id}")
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "get-test-repo"
        assert response_data["id"] == repo.id

    @pytest.mark.asyncio
    async def test_get_repository_not_found(self, async_client: AsyncClient):
        """Test getting non-existent repository."""
        response = await async_client.get("/api/repositories/999")
        
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_repository_success(self, async_client: AsyncClient, test_db: Session):
        """Test updating repository."""
        repo = Repository(name="update-test-repo", path="/tmp/update-test")
        repo.set_passphrase("old-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        update_data = {
            "name": "updated-repo-name",
            "passphrase": "new-passphrase"
        }
        
        response = await async_client.put(f"/api/repositories/{repo.id}", json=update_data)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "updated-repo-name"

    @pytest.mark.asyncio
    async def test_update_repository_not_found(self, async_client: AsyncClient):
        """Test updating non-existent repository."""
        update_data = {"name": "new-name"}
        
        response = await async_client.put("/api/repositories/999", json=update_data)
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_repository_success(self, async_client: AsyncClient, test_db: Session):
        """Test deleting repository."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import DeleteRepositoryResult

        # Create mock success result
        mock_result = DeleteRepositoryResult(
            success=True,
            repository_name="delete-test-repo",
            deleted_schedules=0
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.delete("/api/repositories/1")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_delete_repository_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent repository."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import DeleteRepositoryResult

        # Create mock not found result
        mock_result = DeleteRepositoryResult(
            success=False,
            repository_name="Unknown",
            error_message="Repository not found"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.delete("/api/repositories/999")

            assert response.status_code == 500
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_delete_repository_with_active_jobs(self, async_client: AsyncClient, test_db: Session):
        """Test deleting repository with active jobs."""
        repo = Repository(name="active-jobs-repo", path="/tmp/active-jobs")
        repo.set_passphrase("active-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        # Create active job
        active_job = Job(
            repository_id=repo.id,
            type="backup",
            status="running"
        )
        test_db.add(active_job)
        test_db.commit()
        
        response = await async_client.delete(f"/api/repositories/{repo.id}")
        
        assert response.status_code == 409
        assert "Cannot delete repository" in response.json()["detail"]
        assert "active job(s) running" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_repository_schedule_cleanup(self, async_client: AsyncClient, test_db: Session):
        """Test repository deletion cleans up schedules."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import DeleteRepositoryResult

        # Create mock success result with schedule cleanup
        mock_result = DeleteRepositoryResult(
            success=True,
            repository_name="schedule-cleanup-repo",
            deleted_schedules=1
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.delete_repository.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.delete("/api/repositories/1")

            assert response.status_code == 200
            # Verify delete was called
            mock_repo_service.delete_repository.assert_called_once()
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]


    @pytest.mark.asyncio
    async def test_list_archives_repository_not_found(self, async_client: AsyncClient):
        """Test listing archives for non-existent repository."""
        from app.dependencies import get_repository_service
        from app.services.repositories.repository_service import RepositoryService
        from app.models.repository_dtos import ArchiveListingResult

        # Create mock not found result
        mock_result = ArchiveListingResult(
            success=False,
            repository_id=999,
            repository_name="Unknown",
            archives=[],
            recent_archives=[],
            error_message="Repository not found"
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.list_archives.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get("/api/repositories/999/archives")

            assert response.status_code == 500  # Service layer returns 500 for errors
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]


    @pytest.mark.asyncio
    async def test_list_archives_html_success(self, async_client: AsyncClient, test_db: Session):
        """Test listing archives as HTML."""
        repo = Repository(name="html-archives-repo", path="/tmp/html-archives")
        repo.set_passphrase("html-archives-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        mock_archives = [
            {
                "name": "archive1",
                "time": "2023-01-01T12:00:00Z",
                "stats": {"original_size": 1024000}
            }
        ]
        
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.list_archives.return_value = mock_archives
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/html")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_list_archives_html_error_handling(self, async_client: AsyncClient, test_db: Session):
        """Test archives HTML with error handling."""
        repo = Repository(name="html-error-repo", path="/tmp/html-error")
        repo.set_passphrase("html-error-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.list_archives.side_effect = Exception("List archives error")
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/html")
            
            assert response.status_code == 200  # Returns error template
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_get_archives_repository_selector(self, async_client: AsyncClient, test_db: Session):
        """Test getting archives repository selector."""
        repo = Repository(name="selector-repo", path="/tmp/selector")
        repo.set_passphrase("selector-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        response = await async_client.get("/api/repositories/archives/selector")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_archives_list_empty(self, async_client: AsyncClient):
        """Test getting archives list without repository ID."""
        response = await async_client.get("/api/repositories/archives/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_archives_list_with_repo(self, async_client: AsyncClient, test_db: Session):
        """Test getting archives list with repository ID."""
        repo = Repository(name="list-repo", path="/tmp/list")
        repo.set_passphrase("list-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.list_archives.return_value = []
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get(f"/api/repositories/archives/list?repository_id={repo.id}")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_get_repository_info_success(self, async_client: AsyncClient, test_db: Session):
        """Test getting repository info."""
        repo = Repository(name="info-repo", path="/tmp/info")
        repo.set_passphrase("info-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        mock_info = {
            "repository": {"id": "test-repo-id", "location": "/tmp/info"},
            "encryption": {"mode": "repokey"},
            "cache": {"stats": {"total_size": 1024}}
        }
        
        # Create mock service
        mock_borg_service = AsyncMock(spec=BorgService)
        mock_borg_service.get_repo_info.return_value = mock_info
        
        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service
        
        try:
            response = await async_client.get(f"/api/repositories/{repo.id}/info")
            
            assert response.status_code == 200
            response_data = response.json()
            assert "repository" in response_data
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_get_repository_info_not_found(self, async_client: AsyncClient):
        """Test getting info for non-existent repository."""
        response = await async_client.get("/api/repositories/999/info")
        
        assert response.status_code == 404


    @pytest.mark.asyncio
    async def test_get_archive_contents_not_found(self, async_client: AsyncClient):
        """Test getting contents for non-existent repository."""
        response = await async_client.get("/api/repositories/999/archives/test-archive/contents")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_extract_file_success(self, async_client: AsyncClient, test_db: Session):
        """Test extracting file from archive."""
        repo = Repository(name="extract-repo", path="/tmp/extract")
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
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/test-archive/extract?file=test.txt")
            
            assert response.status_code == 200
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self, async_client: AsyncClient):
        """Test extracting file from non-existent repository."""
        response = await async_client.get("/api/repositories/999/archives/test-archive/extract?file=test.txt")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_stats_selector(self, async_client: AsyncClient, test_db: Session):
        """Test getting repository selector for statistics."""
        # Create test repositories
        repo1 = Repository(name="stats-repo-1", path="/tmp/stats1")
        repo1.set_passphrase("pass1")
        repo2 = Repository(name="stats-repo-2", path="/tmp/stats2")
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
    async def test_get_stats_loading(self, async_client: AsyncClient):
        """Test getting loading state for statistics."""
        response = await async_client.get("/api/repositories/stats/loading?repository_id=1")
        
        assert response.status_code == 200
        # Verify HTML response contains loading template
        content = response.text
        assert "repository_id" in content or "loading" in content.lower()

    @pytest.mark.asyncio
    async def test_get_stats_loading_no_repository(self, async_client: AsyncClient):
        """Test getting loading state without repository ID."""
        response = await async_client.get("/api/repositories/stats/loading")
        
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_stats_content_no_repository(self, async_client: AsyncClient):
        """Test getting stats content without repository ID shows empty state."""
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
        try:
            response = await async_client.get("/api/repositories/stats/content")
            
            assert response.status_code == 200
            # Should show empty state
            content = response.text
            assert "empty" in content.lower() or content.strip() != ""
        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_get_stats_content_with_repository(self, async_client: AsyncClient, test_db: Session):
        """Test getting stats content with valid repository ID."""
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Create test repository
        repo = Repository(name="stats-test-repo", path="/tmp/stats-test")
        repo.set_passphrase("stats-pass")
        test_db.add(repo)
        test_db.commit()
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.return_value = {
            "repository_path": "/tmp/stats-test",
            "total_archives": 5,
            "archive_stats": [],
            "size_over_time": {"count_chart": {"labels": [], "datasets": []}, "size_chart": {"labels": [], "datasets": []}},
            "dedup_compression_stats": {},
            "file_type_stats": {
                "count_chart": {"labels": [], "datasets": []},
                "size_chart": {"labels": [], "datasets": []}
            },
            "summary": {
                "total_archives": 5,
                "latest_archive_date": "2024-01-01",
                "total_original_size_gb": 10.0,
                "total_compressed_size_gb": 7.5,
                "total_deduplicated_size_gb": 5.0,
                "overall_compression_ratio": 25.0,
                "overall_deduplication_ratio": 33.3
            }
        }
        
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
        try:
            response = await async_client.get(f"/api/repositories/stats/content?repository_id={repo.id}")
            
            assert response.status_code == 200
            # Should call the stats service and return HTML
            mock_stats_service.get_repository_statistics.assert_called_once()
            
            # Verify response is HTML (not empty state)
            content = response.text
            assert content.strip() != ""
            
        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_get_stats_content_repository_not_found(self, async_client: AsyncClient):
        """Test getting stats content with non-existent repository ID."""
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
        try:
            response = await async_client.get("/api/repositories/stats/content?repository_id=999")
            
            # Should return 404 for non-existent repository
            assert response.status_code == 404
            
        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_get_repository_statistics_direct(self, async_client: AsyncClient, test_db: Session):
        """Test the direct repository statistics endpoint."""
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Create test repository
        repo = Repository(name="direct-stats-repo", path="/tmp/direct-stats")
        repo.set_passphrase("direct-pass")
        test_db.add(repo)
        test_db.commit()
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.return_value = {
            "repository_path": "/tmp/direct-stats",
            "total_archives": 3,
            "archive_stats": [],
            "size_over_time": {"count_chart": {"labels": ["2024-01-01"], "datasets": []}, "size_chart": {"labels": ["2024-01-01"], "datasets": []}},
            "dedup_compression_stats": {},
            "file_type_stats": {
                "count_chart": {"labels": ["text"], "datasets": [{"data": [100]}]},
                "size_chart": {"labels": ["text"], "datasets": [{"data": [1000]}]}
            },
            "summary": {
                "total_archives": 3,
                "latest_archive_date": "2024-01-01",
                "total_original_size_gb": 5.0,
                "total_compressed_size_gb": 4.0,
                "total_deduplicated_size_gb": 3.0,
                "overall_compression_ratio": 20.0,
                "overall_deduplication_ratio": 25.0
            }
        }
        
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
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
    async def test_get_repository_statistics_not_found(self, async_client: AsyncClient):
        """Test repository statistics endpoint with non-existent repository."""
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
        try:
            response = await async_client.get("/api/repositories/999/stats")
            
            assert response.status_code == 404
            
        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_stats_content_dependency_injection_regression(self, async_client: AsyncClient, test_db: Session):
        """
        Regression test to ensure /api/repositories/stats/content doesn't fail
        with AttributeError: 'Depends' object has no attribute 'query'
        
        This test specifically catches the bug where a FastAPI Depends object
        was being passed instead of the actual database session.
        """
        from app.dependencies import get_repository_stats_service
        from app.services.repositories.repository_stats_service import RepositoryStatsService
        
        # Create test repository
        repo = Repository(name="regression-test-repo", path="/tmp/regression-test")
        repo.set_passphrase("regression-pass")
        test_db.add(repo)
        test_db.commit()
        
        # Mock the stats service
        mock_stats_service = AsyncMock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.return_value = {
            "repository_path": "/tmp/regression-test",
            "total_archives": 1,
            "archive_stats": [],
            "size_over_time": {"count_chart": {"labels": [], "datasets": []}, "size_chart": {"labels": [], "datasets": []}},
            "dedup_compression_stats": {},
            "file_type_stats": {
                "count_chart": {"labels": [], "datasets": []},
                "size_chart": {"labels": [], "datasets": []}
            },
            "summary": {
                "total_archives": 1,
                "latest_archive_date": "2024-01-01",
                "total_original_size_gb": 1.0,
                "total_compressed_size_gb": 1.0,
                "total_deduplicated_size_gb": 1.0,
                "overall_compression_ratio": 0.0,
                "overall_deduplication_ratio": 0.0
            }
        }
        
        app.dependency_overrides[get_repository_stats_service] = lambda: mock_stats_service
        
        try:
            # This should NOT raise AttributeError: 'Depends' object has no attribute 'query'
            response = await async_client.get(f"/api/repositories/stats/content?repository_id={repo.id}")
            
            # The key assertion: should not be a 500 Internal Server Error
            assert response.status_code != 500, f"Got 500 error, likely dependency injection issue: {response.text}"
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            # Should successfully call the stats service
            mock_stats_service.get_repository_statistics.assert_called_once()
            
            # Response should be valid HTML
            content = response.text
            assert content.strip() != ""
            assert "text/html" in response.headers.get("content-type", "").lower()
            
        finally:
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

