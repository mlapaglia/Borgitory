"""
API tests for Repository Management endpoints - HTMX Response Validation.
Tests that endpoints return proper HTML responses for HTMX integration.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import Mock, AsyncMock

from borgitory.main import app
from borgitory.models.database import Repository
from borgitory.dependencies import get_repository_service


class TestRepositoryManagementAPI:
    """Test repository management API endpoints for HTMX responses."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_repository_service(self) -> Mock:
        """Create mock repository service."""
        mock = Mock()
        mock.check_repository_lock_status = AsyncMock()
        mock.break_repository_lock = AsyncMock()
        mock.get_repository_info = AsyncMock()
        mock.export_repository_key = AsyncMock()
        return mock

    @pytest.fixture
    def test_repository(self, test_db: Session) -> Repository:
        """Create test repository in database."""
        repo = Repository()
        repo.name = "test-repo"
        repo.path = "/test/repo/path"
        repo.set_passphrase("test_passphrase")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        return repo

    def test_details_modal_endpoint(
        self, client: TestClient, test_repository: Repository
    ) -> None:
        """Test repository details modal endpoint returns proper HTML."""
        response = client.get(f"/api/repositories/{test_repository.id}/details-modal")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        # Should contain modal structure
        assert "modal-container" in html_content
        assert "Repository Details:" in html_content
        assert test_repository.name in html_content
        assert test_repository.path in html_content
        # Should have HTMX attributes for loading content
        assert "hx-get" in html_content
        assert 'hx-trigger="load"' in html_content

    def test_close_modal_endpoint(self, client: TestClient) -> None:
        """Test close modal endpoint returns empty response."""
        response = client.get("/api/repositories/modal/close")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.text.strip() == ""

    def test_lock_status_endpoint_unlocked(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test lock status endpoint when repository is unlocked."""
        # Configure mock service for unlocked status
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": False,
                "accessible": True,
                "message": "Repository is accessible",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/lock-status")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show unlocked status
            assert "Available" in html_content
            assert "bg-green-100" in html_content or "bg-green-800" in html_content
            assert "Repository is accessible" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_lock_status_endpoint_locked(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test lock status endpoint when repository is locked."""
        # Configure mock service for locked status
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": True,
                "accessible": False,
                "message": "Repository is locked by another process",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/lock-status")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show locked status
            assert "Locked" in html_content
            assert "bg-red-100" in html_content or "bg-red-800" in html_content
            assert "Repository is locked by another process" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_lock_status_endpoint_error(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test lock status endpoint when there's an error."""
        # Configure mock service for error status
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": False,
                "accessible": False,
                "message": "Repository access failed: Connection timeout",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/lock-status")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show error status
            assert "Error" in html_content
            assert "bg-orange-100" in html_content or "bg-orange-800" in html_content
            assert "Repository access failed: Connection timeout" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_break_lock_button_endpoint_locked(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test break lock button endpoint when repository is locked."""
        # Configure mock service
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": True,
                "accessible": False,
                "message": "Repository is locked",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(
                f"/api/repositories/{test_repository.id}/break-lock-button"
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show break lock button
            assert "Break Lock" in html_content
            assert "hx-post" in html_content
            assert "hx-confirm" in html_content
            assert test_repository.name in html_content

        finally:
            app.dependency_overrides.clear()

    def test_break_lock_button_endpoint_unlocked(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test break lock button endpoint when repository is unlocked."""
        # Configure mock service
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": False,
                "accessible": True,
                "message": "Repository is accessible",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(
                f"/api/repositories/{test_repository.id}/break-lock-button"
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should not show break lock button (only HTML comment should be present)
            assert "<button" not in html_content
            assert "hx-post" not in html_content
            # Should only contain the template comment
            assert "<!-- Break Lock Button Template -->" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_break_lock_button_modal_endpoint(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test break lock button modal endpoint."""
        # Configure mock service
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": True,
                "accessible": False,
                "message": "Repository is locked",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(
                f"/api/repositories/{test_repository.id}/break-lock-button-modal"
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show modal-specific break lock button
            assert "Break Lock" in html_content
            assert "hx-post" in html_content
            assert "break-lock-modal" in html_content
            assert "hx-target" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_break_lock_endpoint_success(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test break lock endpoint returns updated repository list."""
        # Configure mock service
        mock_repository_service.break_repository_lock = AsyncMock(
            return_value={"success": True, "message": "Lock successfully removed"}
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.post(f"/api/repositories/{test_repository.id}/break-lock")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should return updated repository list
            assert test_repository.name in html_content
            assert "View Archives" in html_content
            assert "Details" in html_content
            assert "Delete" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_break_lock_modal_endpoint_success(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test break lock modal endpoint returns updated lock status."""
        # Configure mock service
        mock_repository_service.break_repository_lock = AsyncMock(
            return_value={"success": True, "message": "Lock successfully removed"}
        )
        mock_repository_service.check_repository_lock_status = AsyncMock(
            return_value={
                "locked": False,
                "accessible": True,
                "message": "Repository is accessible",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.post(
                f"/api/repositories/{test_repository.id}/break-lock-modal"
            )

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should return updated lock status
            assert "Available" in html_content
            assert "bg-green-100" in html_content or "bg-green-800" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_borg_info_endpoint_success(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test borg info endpoint returns formatted repository details."""
        # Configure mock service
        mock_repository_service.get_repository_info = AsyncMock(
            return_value={
                "success": True,
                "repository_id": "1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b",
                "location": "/test/repo/path",
                "encryption": {"mode": "repokey"},
                "cache": {"path": "/home/user/.cache/borg"},
                "security_dir": "/home/user/.config/borg/security",
                "archives_count": 5,
                "original_size": "1.2 GB",
                "compressed_size": "800.0 MB",
                "deduplicated_size": "600.0 MB",
                "last_modified": "2023-01-01T12:00:00",
                "config": {"additional_free_space": "0", "append_only": "0"},
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/borg-info")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should contain repository details
            assert (
                "1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b"
                in html_content
            )
            assert "/test/repo/path" in html_content
            assert "repokey" in html_content
            assert "5" in html_content  # archives count
            assert "1.2 GB" in html_content
            assert "800.0 MB" in html_content
            assert "600.0 MB" in html_content
            # Should contain config section
            assert "Repository Configuration" in html_content
            assert "additional_free_space" in html_content
            assert "append_only" in html_content
            # Should have proper text wrapping classes
            assert "break-all" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_borg_info_endpoint_error(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test borg info endpoint when there's an error."""
        # Configure mock service
        mock_repository_service.get_repository_info = AsyncMock(
            return_value={
                "success": False,
                "error": True,
                "error_message": "Failed to get repository info: Repository not found",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/borg-info")

            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")

            html_content = response.text
            # Should show error message
            assert "Failed to load repository details" in html_content
            assert "Failed to get repository info: Repository not found" in html_content
            assert "text-red-600" in html_content or "text-red-400" in html_content

        finally:
            app.dependency_overrides.clear()

    def test_export_key_endpoint_success(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test export key endpoint returns downloadable file."""
        # Configure mock service
        mock_repository_service.export_repository_key = AsyncMock(
            return_value={
                "success": True,
                "key_data": "BORG_KEY 1234567890abcdef...",
                "filename": "test-repo_key.txt",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/export-key")

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
            assert "attachment" in response.headers["content-disposition"]
            assert "test-repo_key.txt" in response.headers["content-disposition"]
            assert response.text == "BORG_KEY 1234567890abcdef..."

        finally:
            app.dependency_overrides.clear()

    def test_export_key_endpoint_failure(
        self,
        client: TestClient,
        test_repository: Repository,
        mock_repository_service: Mock,
    ) -> None:
        """Test export key endpoint when export fails."""
        # Configure mock service
        mock_repository_service.export_repository_key = AsyncMock(
            return_value={
                "success": False,
                "error_message": "Failed to export repository key: Key not found",
            }
        )

        app.dependency_overrides[get_repository_service] = (
            lambda: mock_repository_service
        )

        try:
            response = client.get(f"/api/repositories/{test_repository.id}/export-key")

            assert response.status_code == 500
            assert (
                response.json()["detail"]
                == "Failed to export repository key: Key not found"
            )

        finally:
            app.dependency_overrides.clear()
