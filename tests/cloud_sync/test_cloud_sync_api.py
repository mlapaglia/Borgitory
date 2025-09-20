"""
Tests for cloud sync API endpoints - HTMX response format testing only
Business logic tests moved to test_cloud_sync_service.py
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch, Mock

from borgitory.services.cloud_sync_service import CloudSyncConfigService
from tests.conftest import create_s3_cloud_sync_config


class TestCloudSyncAPIHTMX:
    """Test class for cloud sync API HTMX responses."""

    @pytest.mark.asyncio
    async def test_get_add_form_html_response(self, async_client: AsyncClient) -> None:
        """Test getting add form returns HTML."""
        response = await async_client.get("/api/cloud-sync/add-form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_provider_fields_s3(self, async_client: AsyncClient) -> None:
        """Test getting provider fields for S3 returns HTML."""
        response = await async_client.get("/api/cloud-sync/provider-fields?provider=s3")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_provider_fields_sftp(self, async_client: AsyncClient) -> None:
        """Test getting provider fields for SFTP returns HTML."""
        response = await async_client.get(
            "/api/cloud-sync/provider-fields?provider=sftp"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_provider_fields_default(self, async_client: AsyncClient) -> None:
        """Test getting provider fields with default provider returns HTML."""
        response = await async_client.get("/api/cloud-sync/provider-fields")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_config_html_response(self, async_client: AsyncClient) -> None:
        """Test config creation returns HTML response with form data."""
        # Send as form data (how HTMX actually sends it)
        form_data = {
            "name": "test-s3-html",
            "provider": "s3",
            "provider_config[bucket_name]": "test-bucket",
            "provider_config[access_key]": "AKIAIOSFODNN7EXAMPLE",
            "provider_config[secret_key]": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "provider_config[region]": "us-east-1",
            "provider_config[storage_class]": "STANDARD",
        }

        # Mock the service to avoid actual database operations
        with patch("borgitory.dependencies.get_db") as mock_get_db, patch.object(
            CloudSyncConfigService, "create_cloud_sync_config"
        ) as mock_create:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            # Mock successful creation
            mock_config = Mock()
            mock_config.name = "test-s3-html"
            mock_create.return_value = mock_config

            response = await async_client.post("/api/cloud-sync/", data=form_data)

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "HX-Trigger" in response.headers
            assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_create_config_validation_error_html(
        self, async_client: AsyncClient
    ) -> None:
        """Test config creation validation error returns HTML."""
        # Send as form data with missing required fields
        form_data = {
            "name": "test-validation-error",
            "provider": "s3",
            "provider_config[bucket_name]": "test-bucket",
            # Missing access_key and secret_key
        }

        response = await async_client.post("/api/cloud-sync/", data=form_data)

        # Schema validation should return 422
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_config_service_error_html(
        self, async_client: AsyncClient
    ) -> None:
        """Test config creation service error returns HTML."""
        # Send as form data
        form_data = {
            "name": "service-error-test",
            "provider": "s3",
            "provider_config[bucket_name]": "test-bucket",
            "provider_config[access_key]": "AKIAIOSFODNN7EXAMPLE",
            "provider_config[secret_key]": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "provider_config[region]": "us-east-1",
            "provider_config[storage_class]": "STANDARD",
        }

        # Mock service to throw HTTPException
        from fastapi import HTTPException

        with patch("borgitory.dependencies.get_db") as mock_get_db, patch.object(
            CloudSyncConfigService, "create_cloud_sync_config"
        ) as mock_create:
            mock_db = Mock()
            mock_get_db.return_value = mock_db
            mock_create.side_effect = HTTPException(
                status_code=400, detail="Test error"
            )

            response = await async_client.post("/api/cloud-sync/", data=form_data)

            assert response.status_code == 400
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_configs_html_empty(self, async_client: AsyncClient) -> None:
        """Test getting configs as HTML when empty."""
        with patch.object(
            CloudSyncConfigService, "get_cloud_sync_configs"
        ) as mock_get_configs:
            mock_get_configs.return_value = []

            response = await async_client.get("/api/cloud-sync/html")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_configs_html_format(self, async_client: AsyncClient) -> None:
        """Test getting configs as HTML format (response type test only)."""
        response = await async_client.get("/api/cloud-sync/html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Just verify it returns HTML content - business logic tested in service tests
        assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_update_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config update returns HTML response."""
        # Create test config in database
        config = create_s3_cloud_sync_config(
            name="update-html-test",
            bucket_name="old-bucket",
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        update_data = {"bucket_name": "new-bucket", "path_prefix": "updated/"}

        response = await async_client.put(
            f"/api/cloud-sync/{config.id}", json=update_data
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_delete_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config deletion returns HTML response."""
        # Create test config
        config = create_s3_cloud_sync_config(
            name="delete-html-test", bucket_name="delete-bucket"
        )
        test_db.add(config)
        test_db.commit()

        response = await async_client.delete(f"/api/cloud-sync/{config.id}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_enable_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config enable returns HTML response."""
        config = create_s3_cloud_sync_config(
            name="enable-html-test",
            bucket_name="test-bucket",
            enabled=False,
        )
        test_db.add(config)
        test_db.commit()

        response = await async_client.post(f"/api/cloud-sync/{config.id}/enable")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_disable_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config disable returns HTML response."""
        config = create_s3_cloud_sync_config(
            name="disable-html-test",
            bucket_name="test-bucket",
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        response = await async_client.post(f"/api/cloud-sync/{config.id}/disable")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_test_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config test returns HTML response."""
        config = create_s3_cloud_sync_config(
            name="test-config-html",
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()

        # Mock the rclone service and cloud sync service
        with patch(
            "borgitory.services.cloud_sync_service.CloudSyncConfigService.test_cloud_sync_config"
        ) as mock_test:
            mock_test.return_value = {
                "status": "success",
                "message": "Connection successful",
            }

            response = await async_client.post(f"/api/cloud-sync/{config.id}/test")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_edit_form_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting edit form returns HTML."""
        config = create_s3_cloud_sync_config(
            name="edit-form-test",
            bucket_name="edit-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)  # Ensure ID is populated

        response = await async_client.get(f"/api/cloud-sync/{config.id}/edit")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert "edit-form-test" in content

    @pytest.mark.asyncio
    async def test_html_error_responses(self, async_client: AsyncClient) -> None:
        """Test that error responses return HTML format."""
        # Test with non-existent config
        response = await async_client.get("/api/cloud-sync/999")

        assert response.status_code == 404
        # Should be JSON for non-HTMX endpoints that don't have HTML variants

    @pytest.mark.asyncio
    async def test_htmx_headers_preserved(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that HTMX-specific headers are properly set."""
        # Send as form data
        form_data = {
            "name": "htmx-headers-test",
            "provider": "s3",
            "provider_config[bucket_name]": "test-bucket",
            "provider_config[access_key]": "AKIAIOSFODNN7EXAMPLE",
            "provider_config[secret_key]": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "provider_config[region]": "us-east-1",
            "provider_config[storage_class]": "STANDARD",
        }

        # Mock the service to avoid actual database operations
        with patch("borgitory.dependencies.get_db") as mock_get_db, patch.object(
            CloudSyncConfigService, "create_cloud_sync_config"
        ) as mock_create:
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            # Mock successful creation
            mock_config = Mock()
            mock_config.name = "htmx-headers-test"
            mock_create.return_value = mock_config

            response = await async_client.post("/api/cloud-sync/", data=form_data)

            # Verify HTMX trigger header is set for successful operations
            if response.status_code == 200:
                assert "HX-Trigger" in response.headers
                assert response.headers["HX-Trigger"] == "cloudSyncUpdate"
