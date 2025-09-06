"""
Tests for repositories API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock, Mock, mock_open
import tempfile
import os
from io import BytesIO

from app.models.database import Repository, Job, Schedule, User


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
        mock_repos = [
            {"name": "repo1", "path": "/path/to/repo1", "encryption_mode": "repokey"},
            {"name": "repo2", "path": "/path/to/repo2", "encryption_mode": "keyfile"}
        ]
        
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = mock_repos
            
            response = await async_client.get("/api/repositories/scan")
            
            assert response.status_code == 200
            response_data = response.json()
            assert "repositories" in response_data
            assert len(response_data["repositories"]) == 2

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_response(self, async_client: AsyncClient):
        """Test repository scanning with HTMX request."""
        mock_repos = [
            {"name": "htmx-repo", "path": "/path/to/htmx-repo", "encryption_mode": "repokey"}
        ]
        
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = mock_repos
            
            response = await async_client.get(
                "/api/repositories/scan",
                headers={"hx-request": "true"}
            )
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_scan_repositories_service_error(self, async_client: AsyncClient):
        """Test repository scanning with service error."""
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.side_effect = Exception("Scan error")
            
            response = await async_client.get("/api/repositories/scan")
            
            assert response.status_code == 500
            assert "Failed to scan repositories" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_scan_repositories_htmx_error(self, async_client: AsyncClient):
        """Test repository scanning error with HTMX."""
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.side_effect = Exception("Scan error")
            
            response = await async_client.get(
                "/api/repositories/scan",
                headers={"hx-request": "true"}
            )
            
            assert response.status_code == 200  # Returns error template
            assert "text/html" in response.headers["content-type"]

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
        """Test listing directories at root."""
        mock_volumes = ["/data", "/backups"]
        
        with patch('app.services.volume_service.volume_service.get_mounted_volumes',
                   new_callable=AsyncMock) as mock_volumes_fn:
            mock_volumes_fn.return_value = mock_volumes
            
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.isdir', return_value=True), \
                 patch('os.listdir', return_value=["data", "backups", "bin", "etc"]), \
                 patch('os.path.normpath', side_effect=lambda p: p):  # Keep path as-is
                
                response = await async_client.get("/api/repositories/directories?path=/")
                
                assert response.status_code == 200
                response_data = response.json()
                directories = response_data["directories"]
                # Should filter out system directories like bin, etc
                dir_names = [d["name"] for d in directories]
                assert "data" in dir_names
                assert "backups" in dir_names
                assert "bin" not in dir_names
                assert "etc" not in dir_names

    @pytest.mark.asyncio
    async def test_list_directories_valid_path(self, async_client: AsyncClient):
        """Test listing directories at valid path."""
        mock_volumes = ["/data"]
        
        with patch('app.services.volume_service.volume_service.get_mounted_volumes',
                   new_callable=AsyncMock) as mock_volumes_fn:
            mock_volumes_fn.return_value = mock_volumes
            
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.isdir', return_value=True), \
                 patch('os.listdir', return_value=["subdir1", "subdir2"]):
                
                response = await async_client.get("/api/repositories/directories?path=/data")
                
                assert response.status_code == 200
                response_data = response.json()
                directories = response_data["directories"]
                assert len(directories) == 2
                assert directories[0]["name"] == "subdir1"
                assert directories[1]["name"] == "subdir2"

    @pytest.mark.asyncio
    async def test_list_directories_nonexistent_path(self, async_client: AsyncClient):
        """Test listing directories for non-existent path."""
        mock_volumes = ["/data"]
        
        with patch('app.services.volume_service.volume_service.get_mounted_volumes',
                   new_callable=AsyncMock) as mock_volumes_fn:
            mock_volumes_fn.return_value = mock_volumes
            
            with patch('os.path.exists', return_value=False):
                response = await async_client.get("/api/repositories/directories?path=/data/nonexistent")
                
                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []

    @pytest.mark.asyncio
    async def test_list_directories_permission_denied(self, async_client: AsyncClient):
        """Test listing directories with permission denied."""
        mock_volumes = ["/data"]
        
        with patch('app.services.volume_service.volume_service.get_mounted_volumes',
                   new_callable=AsyncMock) as mock_volumes_fn:
            mock_volumes_fn.return_value = mock_volumes
            
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.isdir', return_value=True), \
                 patch('os.listdir', side_effect=PermissionError("Permission denied")):
                
                response = await async_client.get("/api/repositories/directories?path=/data")
                
                assert response.status_code == 200
                response_data = response.json()
                assert response_data["directories"] == []

    @pytest.mark.asyncio
    async def test_list_directories_not_under_mounted_volume(self, async_client: AsyncClient):
        """Test listing directories outside mounted volumes."""
        mock_volumes = ["/data"]
        
        with patch('app.services.volume_service.volume_service.get_mounted_volumes',
                   new_callable=AsyncMock) as mock_volumes_fn:
            mock_volumes_fn.return_value = mock_volumes
            
            response = await async_client.get("/api/repositories/directories?path=/invalid")
            
            assert response.status_code == 500  # API catches HTTPException and converts to 500
            assert "Path must be root directory or under one of the mounted volumes" in response.json()["detail"]

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
        
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = mock_repos
            
            response = await async_client.get("/api/repositories/import-form-update?path=/test/repo")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_update_import_form_repo_not_found(self, async_client: AsyncClient):
        """Test import form update with repository not found."""
        with patch('app.services.borg_service.borg_service.scan_for_repositories',
                   new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = []  # No repositories found
            
            response = await async_client.get("/api/repositories/import-form-update?path=/missing/repo")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_import_repository_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful repository import."""
        with patch('app.services.borg_service.borg_service.verify_repository_access',
                   new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            
            with patch('app.services.borg_service.borg_service.list_archives',
                       new_callable=AsyncMock) as mock_list:
                mock_list.return_value = [{"name": "archive1"}, {"name": "archive2"}]
                
                form_data = {
                    "name": "imported-repo",
                    "path": "/path/to/existing/repo",
                    "passphrase": "existing-passphrase"
                }
                
                response = await async_client.post("/api/repositories/import", data=form_data)
                
                assert response.status_code == 200
                response_data = response.json()
                assert response_data["name"] == "imported-repo"
                
                # Verify repository was created in database
                repo = test_db.query(Repository).filter(Repository.name == "imported-repo").first()
                assert repo is not None

    @pytest.mark.asyncio
    async def test_import_repository_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful repository import via HTMX."""
        with patch('app.services.borg_service.borg_service.verify_repository_access',
                   new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            
            with patch('app.services.borg_service.borg_service.list_archives',
                       new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                
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
        keyfile_content = b"fake-keyfile-content"
        
        with patch('app.services.borg_service.borg_service.verify_repository_access',
                   new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            
            with patch('builtins.open', mock_open()) as mock_file, \
                 patch('os.makedirs'), \
                 patch('app.services.borg_service.borg_service.list_archives',
                       new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                
                files = {"keyfile": ("keyfile.key", BytesIO(keyfile_content), "application/octet-stream")}
                data = {
                    "name": "keyfile-repo",
                    "path": "/path/to/keyfile/repo",
                    "passphrase": "keyfile-passphrase"
                }
                
                response = await async_client.post("/api/repositories/import", data=data, files=files)
                
                assert response.status_code == 200
                mock_file.assert_called()

    @pytest.mark.asyncio
    async def test_import_repository_verification_failure(self, async_client: AsyncClient, test_db: Session):
        """Test repository import with verification failure."""
        with patch('app.services.borg_service.borg_service.verify_repository_access',
                   new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = False  # Verification fails
            
            form_data = {
                "name": "verify-fail-repo",
                "path": "/path/to/bad/repo",
                "passphrase": "wrong-passphrase"
            }
            
            response = await async_client.post("/api/repositories/import", data=form_data)
            
            assert response.status_code == 400
            assert "Failed to verify repository access" in response.json()["detail"]
            
            # Verify repository was not created in database
            repo = test_db.query(Repository).filter(Repository.name == "verify-fail-repo").first()
            assert repo is None

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
        repo = Repository(name="delete-test-repo", path="/tmp/delete-test")
        repo.set_passphrase("delete-passphrase")
        test_db.add(repo)
        test_db.commit()
        repo_id = repo.id
        
        with patch('app.services.scheduler_service.scheduler_service.remove_schedule',
                   new_callable=AsyncMock):
            response = await async_client.delete(f"/api/repositories/{repo_id}")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            
            # Verify repository was deleted
            deleted_repo = test_db.query(Repository).filter(Repository.id == repo_id).first()
            assert deleted_repo is None

    @pytest.mark.asyncio
    async def test_delete_repository_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent repository."""
        response = await async_client.delete("/api/repositories/999")
        
        assert response.status_code == 404

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
        repo = Repository(name="schedule-cleanup-repo", path="/tmp/schedule-cleanup")
        repo.set_passphrase("schedule-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        # Create schedule
        schedule = Schedule(
            repository_id=repo.id,
            name="test-schedule",
            cron_expression="0 2 * * *",
            enabled=True
        )
        test_db.add(schedule)
        test_db.commit()
        
        with patch('app.services.scheduler_service.scheduler_service.remove_schedule',
                   new_callable=AsyncMock) as mock_remove:
            response = await async_client.delete(f"/api/repositories/{repo.id}")
            
            assert response.status_code == 200
            mock_remove.assert_called_once_with(schedule.id)

    @pytest.mark.asyncio
    async def test_list_archives_success(self, async_client: AsyncClient, test_db: Session):
        """Test listing repository archives."""
        repo = Repository(name="archives-test-repo", path="/tmp/archives-test")
        repo.set_passphrase("archives-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        mock_archives = [
            {"name": "archive1", "time": "2023-01-01T12:00:00"},
            {"name": "archive2", "time": "2023-01-02T12:00:00"}
        ]
        
        with patch('app.services.borg_service.borg_service.list_archives',
                   new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_archives
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives")
            
            assert response.status_code == 200
            response_data = response.json()
            assert "archives" in response_data
            assert len(response_data["archives"]) == 2

    @pytest.mark.asyncio
    async def test_list_archives_repository_not_found(self, async_client: AsyncClient):
        """Test listing archives for non-existent repository."""
        response = await async_client.get("/api/repositories/999/archives")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_archives_borg_service_error(self, async_client: AsyncClient, test_db: Session):
        """Test listing archives with Borg service error."""
        repo = Repository(name="borg-error-repo", path="/tmp/borg-error")
        repo.set_passphrase("borg-error-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        with patch('app.services.borg_service.borg_service.list_archives',
                   new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = Exception("Borg error")
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives")
            
            assert response.status_code == 500
            assert "Failed to list archives" in response.json()["detail"]

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
        
        with patch('app.services.borg_service.borg_service.list_archives',
                   new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_archives
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/html")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_list_archives_html_error_handling(self, async_client: AsyncClient, test_db: Session):
        """Test archives HTML with error handling."""
        repo = Repository(name="html-error-repo", path="/tmp/html-error")
        repo.set_passphrase("html-error-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        with patch('app.services.borg_service.borg_service.list_archives',
                   new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = Exception("List archives error")
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/html")
            
            assert response.status_code == 200  # Returns error template
            assert "text/html" in response.headers["content-type"]

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
        
        with patch('app.services.borg_service.borg_service.list_archives',
                   new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            
            response = await async_client.get(f"/api/repositories/archives/list?repository_id={repo.id}")
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

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
        
        with patch('app.services.borg_service.borg_service.get_repo_info',
                   new_callable=AsyncMock) as mock_info_fn:
            mock_info_fn.return_value = mock_info
            
            response = await async_client.get(f"/api/repositories/{repo.id}/info")
            
            assert response.status_code == 200
            response_data = response.json()
            assert "repository" in response_data

    @pytest.mark.asyncio
    async def test_get_repository_info_not_found(self, async_client: AsyncClient):
        """Test getting info for non-existent repository."""
        response = await async_client.get("/api/repositories/999/info")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_archive_contents_success(self, async_client: AsyncClient, test_db: Session):
        """Test getting archive contents."""
        repo = Repository(name="contents-repo", path="/tmp/contents")
        repo.set_passphrase("contents-passphrase")
        test_db.add(repo)
        test_db.commit()
        
        mock_contents = [
            {"path": "file1.txt", "type": "f", "size": 100},
            {"path": "dir1", "type": "d", "size": 0}
        ]
        
        with patch('app.services.borg_service.borg_service.list_archive_directory_contents',
                   new_callable=AsyncMock) as mock_contents_fn:
            mock_contents_fn.return_value = mock_contents
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/test-archive/contents")
            
            assert response.status_code == 200
            response_data = response.json()
            assert "items" in response_data
            assert len(response_data["items"]) == 2

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
        
        with patch('app.services.borg_service.borg_service.extract_file_stream',
                   new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = mock_file_stream
            
            response = await async_client.get(f"/api/repositories/{repo.id}/archives/test-archive/extract?file=test.txt")
            
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self, async_client: AsyncClient):
        """Test extracting file from non-existent repository."""
        response = await async_client.get("/api/repositories/999/archives/test-archive/extract?file=test.txt")
        
        assert response.status_code == 404

