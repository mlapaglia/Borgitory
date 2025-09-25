"""
Tests for tabs API endpoints
"""

import pytest
from typing import Any, Generator
from unittest.mock import Mock
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.api.auth import get_current_user
from borgitory.models.database import User
from borgitory.dependencies import get_provider_registry


@pytest.fixture
def mock_current_user(test_db: Session) -> Generator[User, None, None]:
    """Create a mock current user for testing."""
    test_user = User()
    test_user.username = "testuser"
    test_user.set_password("testpass")
    test_db.add(test_user)
    test_db.commit()
    test_db.refresh(test_user)

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield test_user
    app.dependency_overrides.clear()


class TestTabsAPI:
    """Test class for tabs API endpoints."""

    @pytest.mark.asyncio
    async def test_get_repositories_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting repositories tab content."""
        response = await async_client.get("/api/tabs/repositories")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_backups_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting backups tab content."""
        response = await async_client.get("/api/tabs/backups")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_schedules_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting schedules tab content."""
        response = await async_client.get("/api/tabs/schedules")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting cloud sync tab content."""
        response = await async_client.get("/api/tabs/cloud-sync")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab_contains_provider_dropdown(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
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
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test that cloud sync tab uses registry to get providers."""
        from borgitory.services.cloud_providers.registry import CloudProviderInfo

        # Create a mock registry
        mock_registry = Mock()
        mock_provider_info = CloudProviderInfo(
            name="mock_provider",
            label="Mock Provider",
            description="Test provider",
            config_class="MockConfig",
            storage_class="MockStorage",
            supports_encryption=True,
            supports_versioning=False,
            requires_credentials=True,
            additional_info={},
            rclone_mapping=None,
        )
        mock_registry.get_all_provider_info.return_value = {
            "mock_provider": mock_provider_info
        }

        # Override the registry dependency
        app.dependency_overrides[get_provider_registry] = lambda: mock_registry

        try:
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
        finally:
            # Clean up dependency override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_cloud_sync_tab_empty_providers(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test cloud sync tab behavior when no providers are registered."""
        # Create a mock registry with no providers
        mock_registry = Mock()
        mock_registry.get_all_provider_info.return_value = {}

        # Override the registry dependency
        app.dependency_overrides[get_provider_registry] = lambda: mock_registry

        try:
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
        finally:
            # Clean up dependency override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_provider_fields_endpoint_uses_registry_for_submit_text(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test that provider fields endpoint uses registry for submit button text."""
        # Test with S3 provider
        response = await async_client.get("/api/cloud-sync/provider-fields?provider=s3")
        assert response.status_code == 200
        content = response.text
        assert "Add AWS S3 Location" in content

        # Test with SFTP provider
        response = await async_client.get(
            "/api/cloud-sync/provider-fields?provider=sftp"
        )
        assert response.status_code == 200
        content = response.text
        assert "Add SFTP (SSH) Location" in content

        # Test with SMB provider
        response = await async_client.get(
            "/api/cloud-sync/provider-fields?provider=smb"
        )
        assert response.status_code == 200
        content = response.text
        assert "Add SMB/CIFS Location" in content

        # Test with empty provider (should not show submit button)
        response = await async_client.get("/api/cloud-sync/provider-fields?provider=")
        assert response.status_code == 200
        content = response.text
        # Should not have submit button when provider is empty
        assert "submit-button" not in content

    @pytest.mark.asyncio
    async def test_provider_fields_endpoint_handles_unknown_provider(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test that provider fields endpoint handles unknown providers gracefully."""
        response = await async_client.get(
            "/api/cloud-sync/provider-fields?provider=unknown"
        )
        assert response.status_code == 200
        content = response.text
        assert "Add Sync Location" in content  # Should fallback to generic text

    @pytest.mark.asyncio
    async def test_get_archives_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting archives tab content."""
        response = await async_client.get("/api/tabs/archives")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_archives_tab_with_preselect_repo(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting archives tab with preselected repository."""
        response = await async_client.get("/api/tabs/archives?preselect_repo=123")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

        # Check that preselect_repo parameter is passed to template
        content = response.text
        assert "preselect_repo=123" in content

    @pytest.mark.asyncio
    async def test_get_statistics_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting statistics tab content."""
        response = await async_client.get("/api/tabs/statistics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_jobs_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting jobs tab content."""
        response = await async_client.get("/api/tabs/jobs")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_notifications_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting notifications tab content."""
        response = await async_client.get("/api/tabs/notifications")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_prune_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting prune tab content."""
        response = await async_client.get("/api/tabs/prune")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_repository_check_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting repository check tab content."""
        response = await async_client.get("/api/tabs/repository-check")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_get_debug_tab(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
        """Test getting debug tab content."""
        response = await async_client.get("/api/tabs/debug")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    @pytest.mark.asyncio
    async def test_tabs_require_authentication(self, async_client: AsyncClient) -> None:
        """Test that tabs endpoints require authentication."""
        # Without mocking auth, this should fail
        response = await async_client.get("/api/tabs/repositories")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_all_tabs_return_html(
        self, async_client: AsyncClient, mock_current_user: Any
    ) -> None:
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
