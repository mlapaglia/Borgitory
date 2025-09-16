"""
Tests for tabs API endpoints
"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.orm import Session

from main import app
from api.auth import get_current_user
from models.database import User


@pytest.fixture
def mock_current_user(test_db: Session):
    """Create a mock current user for testing."""
    test_user = User(username="testuser")
    test_user.set_password("testpass")
    test_db.add(test_user)
    test_db.commit()
    test_db.refresh(test_user)

    def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield test_user
    app.dependency_overrides.clear()


class TestTabsAPI:
    """Test class for tabs API endpoints."""

    @pytest.mark.asyncio
    async def test_get_repositories_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting repositories tab content."""
        response = await async_client.get("/api/tabs/repositories")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_backups_tab(self, async_client: AsyncClient, mock_current_user):
        """Test getting backups tab content."""
        response = await async_client.get("/api/tabs/backups")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_schedules_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting schedules tab content."""
        response = await async_client.get("/api/tabs/schedules")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting cloud sync tab content."""
        response = await async_client.get("/api/tabs/cloud-sync")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab_contains_provider_dropdown(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test that cloud sync tab contains provider dropdown with options."""
        response = await async_client.get("/api/tabs/cloud-sync")
        assert response.status_code == 200

        content = response.text

        # Check that the provider dropdown exists
        assert 'name="provider"' in content
        assert 'id="provider-select"' in content
        assert "Select Provider Type" in content

        # Check that provider options are populated from the registry
        assert 'value="s3"' in content
        assert 'value="sftp"' in content
        assert 'value="smb"' in content

        # Check that provider labels are present
        assert "AWS S3" in content
        assert "SFTP (SSH)" in content
        assert "SMB/CIFS" in content

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab_uses_registry(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test that cloud sync tab uses registry to get providers."""
        # Mock the registry function to return specific providers
        mock_providers = [
            {
                "value": "mock_provider",
                "label": "Mock Provider",
                "description": "Test provider",
            }
        ]

        with patch(
            "api.cloud_sync._get_supported_providers", return_value=mock_providers
        ):
            response = await async_client.get("/api/tabs/cloud-sync")
            assert response.status_code == 200

            content = response.text
            # Should contain our mocked provider
            assert 'value="mock_provider"' in content
            assert "Mock Provider" in content

            # Should NOT contain real providers since we mocked them
            assert 'value="s3"' not in content
            assert 'value="sftp"' not in content
            assert 'value="smb"' not in content

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab_empty_providers(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test cloud sync tab behavior when no providers are registered."""
        # Mock registry to return empty list
        with patch("api.cloud_sync._get_supported_providers", return_value=[]):
            response = await async_client.get("/api/tabs/cloud-sync")
            assert response.status_code == 200

            content = response.text
            # Should still have the dropdown structure
            assert 'name="provider"' in content
            assert 'id="provider-select"' in content
            assert "Select Provider Type" in content

            # But no provider options
            assert 'value="s3"' not in content
            assert 'value="sftp"' not in content
            assert 'value="smb"' not in content

    @pytest.mark.asyncio
    async def test_get_archives_tab(self, async_client: AsyncClient, mock_current_user):
        """Test getting archives tab content."""
        response = await async_client.get("/api/tabs/archives")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_statistics_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting statistics tab content."""
        response = await async_client.get("/api/tabs/statistics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_jobs_tab(self, async_client: AsyncClient, mock_current_user):
        """Test getting jobs tab content."""
        response = await async_client.get("/api/tabs/jobs")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_notifications_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting notifications tab content."""
        response = await async_client.get("/api/tabs/notifications")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_cleanup_tab(self, async_client: AsyncClient, mock_current_user):
        """Test getting cleanup tab content."""
        response = await async_client.get("/api/tabs/prune")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_repository_check_tab(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test getting repository check tab content."""
        response = await async_client.get("/api/tabs/repository-check")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_debug_tab(self, async_client: AsyncClient, mock_current_user):
        """Test getting debug tab content."""
        response = await async_client.get("/api/tabs/debug")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_tabs_require_authentication(self, async_client: AsyncClient):
        """Test that tabs endpoints require authentication."""
        # Without mocking auth, this should fail
        response = await async_client.get("/api/tabs/repositories")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_all_tabs_return_html(
        self, async_client: AsyncClient, mock_current_user
    ):
        """Test that all tab endpoints return HTML content."""
        endpoints = [
            "/api/tabs/repositories",
            "/api/tabs/backups",
            "/api/tabs/schedules",
            "/api/tabs/cloud-sync",
            "/api/tabs/archives",
            "/api/tabs/statistics",
            "/api/tabs/jobs",
            "/api/tabs/notifications",
            "/api/tabs/prune",
            "/api/tabs/repository-check",
            "/api/tabs/debug",
        ]

        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
