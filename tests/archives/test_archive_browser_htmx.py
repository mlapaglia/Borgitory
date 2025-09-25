"""
Tests for archive browser HTMX functionality
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import Mock, AsyncMock

from borgitory.main import app
from borgitory.models.database import Repository
from borgitory.dependencies import get_borg_service
from borgitory.services.borg_service import BorgService


class TestArchiveBrowserHTMX:
    """Test class for archive browser HTMX functionality."""

    @pytest.mark.asyncio
    async def test_list_archives_htmx_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test listing archives via HTMX returns HTML template."""
        repo = Repository()
        repo.name = "htmx-test-repo"
        repo.path = "/tmp/htmx-test"
        repo.set_passphrase("htmx-passphrase")
        test_db.add(repo)
        test_db.commit()

        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import ArchiveListingResult, ArchiveInfo

        mock_archives = [
            ArchiveInfo(name="archive1", time="2023-01-01T10:00:00"),
            ArchiveInfo(name="archive2", time="2023-01-02T10:00:00"),
        ]

        # Create mock success result
        mock_result = ArchiveListingResult(
            success=True,
            repository_id=repo.id,
            repository_name="htmx-test-repo",
            archives=mock_archives,
            recent_archives=mock_archives,
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.list_archives.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            # Make HTMX request
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives", headers={"hx-request": "true"}
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check for archive names in HTML
            assert "archive1" in response.text
            assert "archive2" in response.text

            # Check for proper HTML structure (archive list uses different classes)
            assert (
                'class="border dark:border-gray-600' in response.text
            )  # Archive cards
            assert "View Contents" in response.text
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_list_archives_htmx_empty(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test listing archives when repository has no archives."""
        repo = Repository()
        repo.name = "empty-repo"
        repo.path = "/tmp/empty"
        repo.set_passphrase("empty-passphrase")
        test_db.add(repo)
        test_db.commit()

        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import ArchiveListingResult

        # Create mock empty result
        mock_result = ArchiveListingResult(
            success=True,
            repository_id=repo.id,
            repository_name="empty-repo",
            archives=[],
            recent_archives=[],
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.list_archives.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives", headers={"hx-request": "true"}
            )

            assert response.status_code == 200

            # Should show empty state message
            assert (
                "No Archives Found" in response.text
                or "doesn't contain any backup archives" in response.text
            )
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_list_archives_htmx_error(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test listing archives when service throws error."""
        repo = Repository()
        repo.name = "error-repo"
        repo.path = "/tmp/error"
        repo.set_passphrase("error-passphrase")
        test_db.add(repo)
        test_db.commit()

        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import ArchiveListingResult

        # Create mock error result
        mock_result = ArchiveListingResult(
            success=False,
            repository_id=repo.id,
            repository_name="error-repo",
            archives=[],
            recent_archives=[],
            error_message="Repository access failed",
        )

        # Create mock repository service
        mock_repo_service = AsyncMock(spec=RepositoryService)
        mock_repo_service.list_archives.return_value = mock_result

        # Override the repository service dependency
        app.dependency_overrides[get_repository_service] = lambda: mock_repo_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives", headers={"hx-request": "true"}
            )

            assert response.status_code == 200

            # Should show error message
            assert "Error Loading Archives" in response.text
            assert "Repository access failed" in response.text
        finally:
            # Clean up
            if get_repository_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_service]

    @pytest.mark.asyncio
    async def test_list_archives_htmx_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing archives for non-existent repository."""
        from borgitory.dependencies import get_repository_service
        from borgitory.services.repositories.repository_service import RepositoryService
        from borgitory.models.repository_dtos import ArchiveListingResult

        # Create mock not found result
        mock_result = ArchiveListingResult(
            success=False,
            repository_id=9999,
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
            response = await async_client.get(
                "/api/repositories/9999/archives", headers={"hx-request": "true"}
            )

            assert response.status_code == 200  # Returns error template, not HTTP error
            assert (
                "Error Loading Archives" in response.text
                or "Repository not found" in response.text
            )
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_contents_htmx_success(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting archive contents via HTMX returns HTML template."""
        repo = Repository()
        repo.name = "contents-repo"
        repo.path = "/tmp/contents"
        repo.set_passphrase("contents-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_contents = [
            {
                "name": "file1.txt",
                "path": "file1.txt",
                "is_directory": False,
                "size": 1024,
                "modified": "2023-01-01T10:00:00",
            },
            {
                "name": "dir1",
                "path": "dir1",
                "is_directory": True,
                "size": None,
                "modified": "2023-01-01T09:00:00",
            },
        ]

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            return_value=mock_contents
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

            # Check for files and directories
            assert "file1.txt" in response.text
            assert "dir1" in response.text

            # Check for proper HTML structure
            assert 'class="archive-browser"' in response.text
            assert 'class="directory-contents"' in response.text

            # Check breadcrumb navigation
            assert "breadcrumb-nav" in response.text
            assert "Root Directory" in response.text

            # Check file size formatting
            assert "1.0 KB" in response.text

            # Check download links for files
            assert "extract" in response.text and "href=" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_contents_htmx_with_path(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting archive contents with specific path."""
        repo = Repository()
        repo.name = "contents-path-repo"
        repo.path = "/tmp/contents-path"
        repo.set_passphrase("contents-path-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_contents = [
            {
                "name": "subfile.txt",
                "path": "subdir/subfile.txt",
                "is_directory": False,
                "size": 2048,
                "modified": "2023-01-01T10:00:00",
            }
        ]

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            return_value=mock_contents
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents?path=subdir",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200

            # Check breadcrumb shows path
            assert "subdir" in response.text

            # Check file content
            assert "subfile.txt" in response.text
            assert "2.0 KB" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_contents_htmx_empty_directory(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting contents of empty directory."""
        repo = Repository()
        repo.name = "empty-dir-repo"
        repo.path = "/tmp/empty-dir"
        repo.set_passphrase("empty-dir-passphrase")
        test_db.add(repo)
        test_db.commit()

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(return_value=[])

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents?path=empty",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200

            # Check for empty directory message
            assert "This directory is empty" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_contents_htmx_error(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test archive contents when service throws error."""
        repo = Repository()
        repo.name = "contents-error-repo"
        repo.path = "/tmp/contents-error"
        repo.set_passphrase("contents-error-passphrase")
        test_db.add(repo)
        test_db.commit()

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            side_effect=Exception("Archive not found")
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200

            # Should show error message
            assert "Error loading directory contents" in response.text
            assert "Archive not found" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_contents_htmx_not_found(
        self, async_client: AsyncClient
    ) -> None:
        """Test archive contents for non-existent repository."""
        response = await async_client.get(
            "/api/repositories/9999/archives/test-archive/contents",
            headers={"hx-request": "true"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_file_size_formatting(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test various file size formatting in templates."""
        repo = Repository()
        repo.name = "size-repo"
        repo.path = "/tmp/size"
        repo.set_passphrase("size-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_contents = [
            {
                "name": "tiny.txt",
                "path": "tiny.txt",
                "is_directory": False,
                "size": 100,
                "modified": "2023-01-01T10:00:00",
            },
            {
                "name": "small.txt",
                "path": "small.txt",
                "is_directory": False,
                "size": 2048,
                "modified": "2023-01-01T10:00:00",
            },
            {
                "name": "medium.txt",
                "path": "medium.txt",
                "is_directory": False,
                "size": 5242880,
                "modified": "2023-01-01T10:00:00",
            },  # 5MB
            {
                "name": "large.txt",
                "path": "large.txt",
                "is_directory": False,
                "size": 2147483648,
                "modified": "2023-01-01T10:00:00",
            },  # 2GB
        ]

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            return_value=mock_contents
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200

            # Check various size formats
            assert "100 B" in response.text
            assert "2.0 KB" in response.text
            assert "5.0 MB" in response.text
            assert "2.0 GB" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_archive_repository_selector(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test the repository selector for archives."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "repo-1"
        repo1.path = "/tmp/repo-1"
        repo1.set_passphrase("pass1")
        repo2 = Repository()
        repo2.name = "repo-2"
        repo2.path = "/tmp/repo-2"
        repo2.set_passphrase("pass2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        response = await async_client.get(
            "/api/repositories/archives/selector", headers={"hx-request": "true"}
        )

        assert response.status_code == 200

        # Check select element has HTMX attributes
        assert 'id="archive-repository-select"' in response.text
        assert "hx-post" in response.text
        assert "hx-target" in response.text
        assert "hx-trigger" in response.text

        # Check repositories are in options
        assert "repo-1" in response.text
        assert "repo-2" in response.text

        # Check refresh button has HTMX attributes
        assert 'id="refresh-archives-btn"' in response.text
        assert "hx-include" in response.text

    @pytest.mark.asyncio
    async def test_archive_repository_selector_with_preselection(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test the repository selector with preselected repository."""
        # Create test repositories
        repo1 = Repository()
        repo1.name = "repo-1"
        repo1.path = "/tmp/repo-1"
        repo1.set_passphrase("pass1")
        repo2 = Repository()
        repo2.name = "repo-2"
        repo2.path = "/tmp/repo-2"
        repo2.set_passphrase("pass2")

        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Test with preselected repository
        response = await async_client.get(
            f"/api/repositories/archives/selector?preselect_repo={repo1.id}",
            headers={"hx-request": "true"},
        )

        assert response.status_code == 200
        content = response.text

        # Check that the correct repository is selected
        assert f'value="{repo1.id}" selected' in content
        assert f'value="{repo2.id}" selected' not in content

        # Check that HTMX trigger includes load when preselected
        assert "hx-trigger" in content
        assert "change" in content

        # Check repositories are still in options
        assert "repo-1" in content
        assert "repo-2" in content

    @pytest.mark.asyncio
    async def test_archive_repository_selector_htmx_triggers(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that HTMX triggers are properly configured for preselection."""
        # Create test repository
        repo = Repository()
        repo.name = "test-repo"
        repo.path = "/tmp/test-repo"
        repo.set_passphrase("testpass")
        test_db.add(repo)
        test_db.commit()

        # Test without preselection - should only have 'change' trigger
        response = await async_client.get(
            "/api/repositories/archives/selector", headers={"hx-request": "true"}
        )
        assert response.status_code == 200
        content = response.text
        assert 'hx-trigger="change"' in content

        # Test with preselection - should have 'change, load' trigger
        response = await async_client.get(
            f"/api/repositories/archives/selector?preselect_repo={repo.id}",
            headers={"hx-request": "true"},
        )
        assert response.status_code == 200
        content = response.text
        assert 'hx-trigger="change, load"' in content

    @pytest.mark.asyncio
    async def test_archives_list_endpoint_form_data(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test archives/list endpoint handles form data from selector."""
        repo = Repository()
        repo.name = "form-repo"
        repo.path = "/tmp/form"
        repo.set_passphrase("form-passphrase")
        test_db.add(repo)
        test_db.commit()

        # Import the dataclass
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Create mock archive using the new dataclass
        mock_archive = BorgArchive(
            name="form-archive",
            id="archive_123",
            start="2023-01-01T10:00:00",
            end="2023-01-01T11:00:00",
            duration=3600.0,
        )

        # Create mock response object
        mock_archives_response = BorgArchiveListResponse(archives=[mock_archive])

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archives = AsyncMock(return_value=mock_archives_response)

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            # Test with form data (simulating select change)
            response = await async_client.get(
                f"/api/repositories/archives/list?repository_id={repo.id}",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200
            assert "form-archive" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_htmx_navigation_attributes(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that HTMX navigation attributes are present in archive browser."""
        repo = Repository()
        repo.name = "nav-repo"
        repo.path = "/tmp/nav"
        repo.set_passphrase("nav-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_contents = [
            {
                "name": "documents",
                "path": "documents",
                "is_directory": True,
                "size": None,
                "modified": "2023-01-01T09:00:00",
            }
        ]

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            return_value=mock_contents
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200

            # Check for HTMX attributes in navigation elements
            assert "hx-post" in response.text
            assert "hx-target" in response.text
            assert "hx-swap" in response.text

            # Check for directory navigation
            assert "documents" in response.text

            # Check breadcrumb navigation
            assert "Root" in response.text or "Root Directory" in response.text
        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]

    @pytest.mark.asyncio
    async def test_breadcrumb_navigation_paths(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that breadcrumb navigation generates correct paths for nested directories."""
        repo = Repository()
        repo.name = "breadcrumb-repo"
        repo.path = "/tmp/breadcrumb"
        repo.set_passphrase("breadcrumb-passphrase")
        test_db.add(repo)
        test_db.commit()

        mock_contents = [
            {
                "name": "file.txt",
                "path": "mnt/backup-sources/1990/file.txt",
                "isdir": False,
                "size": 1024,
                "mtime": "2023-01-01T10:00:00",
            }
        ]

        # Create mock service
        mock_borg_service = Mock(spec=BorgService)
        mock_borg_service.list_archive_directory_contents = AsyncMock(
            return_value=mock_contents
        )

        # Override dependency injection
        app.dependency_overrides[get_borg_service] = lambda: mock_borg_service

        try:
            # Test with nested path
            response = await async_client.get(
                f"/api/repositories/{repo.id}/archives/test-archive/contents?path=mnt/backup-sources/1990",
                headers={"hx-request": "true"},
            )

            assert response.status_code == 200
            response_text = response.text

            # Check that breadcrumb paths are correctly generated
            # Root button should not have hx-vals (defaults to empty path)
            assert "Root" in response_text and "</button>" in response_text

            # First breadcrumb (mnt) should have path="mnt"
            assert 'hx-vals=\'{"path": "mnt"}\'' in response_text

            # Second breadcrumb (backup-sources) should have path="mnt/backup-sources"
            assert 'hx-vals=\'{"path": "mnt/backup-sources"}\'' in response_text

            # Third part (1990) should be displayed as text, not a link
            assert "1990</span>" in response_text  # Should be in a span, not a button

            # Verify the breadcrumb structure shows all parts
            assert "mnt" in response_text
            assert "backup-sources" in response_text
            assert "1990" in response_text

        finally:
            # Clean up
            if get_borg_service in app.dependency_overrides:
                del app.dependency_overrides[get_borg_service]
