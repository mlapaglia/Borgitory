"""
Tests for tabs API endpoints
"""

import pytest
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
        response = await async_client.get("/api/tabs/cleanup")
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
            "/api/tabs/cleanup",
            "/api/tabs/repository-check",
            "/api/tabs/debug",
        ]

        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
