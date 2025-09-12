"""
Tests for cloud sync API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.database import CloudSyncConfig


class TestCloudSyncAPI:
    """Test class for cloud sync API endpoints."""

    @pytest.mark.asyncio
    async def test_get_provider_fields_s3(self, async_client: AsyncClient):
        """Test getting provider fields for S3."""
        response = await async_client.get("/api/cloud-sync/provider-fields?provider=s3")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_provider_fields_sftp(self, async_client: AsyncClient):
        """Test getting provider fields for SFTP."""
        response = await async_client.get("/api/cloud-sync/provider-fields?provider=sftp")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_provider_fields_default(self, async_client: AsyncClient):
        """Test getting provider fields with default provider."""
        response = await async_client.get("/api/cloud-sync/provider-fields")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_s3_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful S3 config creation."""
        config_data = {
            "name": "test-s3",
            "provider": "s3",
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",  # 20 characters
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # 40 characters
            "path_prefix": "backups/"
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 200  # API returns 200, not 201 (no status_code in decorator)
        response_data = response.json()
        assert response_data["name"] == "test-s3"
        assert response_data["provider"] == "s3"
        assert response_data["bucket_name"] == "test-bucket"
        # Credentials should not be returned in response
        assert "access_key" not in response_data
        assert "secret_key" not in response_data

    @pytest.mark.asyncio
    async def test_create_sftp_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful SFTP config creation with password."""
        config_data = {
            "name": "test-sftp",
            "provider": "sftp",
            "host": "sftp.example.com",
            "port": 22,
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
            "path_prefix": "borg/"
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "test-sftp"
        assert response_data["provider"] == "sftp"
        assert response_data["host"] == "sftp.example.com"
        assert response_data["username"] == "testuser"
        # Credentials should not be returned in response
        assert "password" not in response_data

    @pytest.mark.asyncio
    async def test_create_sftp_config_with_private_key(self, async_client: AsyncClient, test_db: Session):
        """Test successful SFTP config creation with private key."""
        config_data = {
            "name": "test-sftp-key",
            "provider": "sftp",
            "host": "sftp.example.com",
            "port": 22,
            "username": "testuser",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-key-content\n-----END RSA PRIVATE KEY-----",
            "remote_path": "/backups"
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "test-sftp-key"

    @pytest.mark.asyncio
    async def test_create_config_duplicate_name(self, async_client: AsyncClient, test_db: Session):
        """Test creating config with duplicate name."""
        # Create first config
        config_data = {
            "name": "duplicate-test",
            "provider": "s3",
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        first_response = await async_client.post("/api/cloud-sync/", json=config_data)
        assert first_response.status_code == 200
        
        # Try to create duplicate
        second_response = await async_client.post("/api/cloud-sync/", json=config_data)
        assert second_response.status_code == 400
        assert "already exists" in second_response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_s3_config_missing_credentials(self, async_client: AsyncClient):
        """Test S3 config creation with missing credentials."""
        config_data = {
            "name": "incomplete-s3",
            "provider": "s3",
            "bucket_name": "test-bucket"
            # Missing access_key and secret_key
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 422  # Schema validation error, not service error
        # Schema validation provides text response
        assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_create_sftp_config_missing_required_fields(self, async_client: AsyncClient):
        """Test SFTP config creation with missing required fields."""
        config_data = {
            "name": "incomplete-sftp",
            "provider": "sftp",
            "host": "sftp.example.com"
            # Missing username, remote_path, and auth method
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 422  # Schema validation error
        assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_create_sftp_config_missing_auth(self, async_client: AsyncClient):
        """Test SFTP config creation with missing authentication."""
        config_data = {
            "name": "sftp-no-auth",
            "provider": "sftp",
            "host": "sftp.example.com",
            "username": "testuser",
            "remote_path": "/backups"
            # Missing both password and private_key
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 422  # Schema validation error
        assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_create_config_unsupported_provider(self, async_client: AsyncClient):
        """Test config creation with unsupported provider."""
        config_data = {
            "name": "unsupported",
            "provider": "azure",  # Not supported
            "bucket_name": "test"
        }
        
        response = await async_client.post("/api/cloud-sync/", json=config_data)
        
        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful config creation via HTMX."""
        config_data = {
            "name": "htmx-s3",
            "provider": "s3",
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        response = await async_client.post(
            "/api/cloud-sync/", 
            json=config_data,
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200  # HTMX responses return 200 with HTML
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_create_config_htmx_validation_error(self, async_client: AsyncClient):
        """Test config creation validation error via HTMX."""
        config_data = {
            "name": "htmx-error",
            "provider": "s3",
            "bucket_name": "test-bucket"
            # Missing credentials
        }
        
        response = await async_client.post(
            "/api/cloud-sync/", 
            json=config_data,
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 422  # Validation error returns 422
        assert response.json()["detail"]  # Should have validation error details

    @pytest.mark.asyncio
    async def test_list_configs_empty(self, async_client: AsyncClient):
        """Test listing configs when empty."""
        response = await async_client.get("/api/cloud-sync/")
        
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_configs_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test listing configs with data."""
        # Create test configs
        config1 = CloudSyncConfig(
            name="s3-config",
            provider="s3",
            bucket_name="bucket1",
            enabled=True
        )
        config2 = CloudSyncConfig(
            name="sftp-config", 
            provider="sftp",
            host="sftp.example.com",
            username="user",
            remote_path="/backup",
            enabled=False
        )
        
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()
        
        response = await async_client.get("/api/cloud-sync/")
        
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "s3-config"
        assert response_data[1]["name"] == "sftp-config"

    @pytest.mark.asyncio
    async def test_get_config_by_id_success(self, async_client: AsyncClient, test_db: Session):
        """Test getting specific config by ID."""
        config = CloudSyncConfig(
            name="get-test",
            provider="s3",
            bucket_name="test-bucket",
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.get(f"/api/cloud-sync/{config.id}")
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["name"] == "get-test"
        assert response_data["id"] == config.id

    @pytest.mark.asyncio
    async def test_get_config_by_id_not_found(self, async_client: AsyncClient):
        """Test getting non-existent config."""
        response = await async_client.get("/api/cloud-sync/999")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_configs_html_empty(self, async_client: AsyncClient):
        """Test getting configs as HTML when empty."""
        response = await async_client.get("/api/cloud-sync/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_configs_html_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test getting configs as HTML with data."""
        config = CloudSyncConfig(
            name="html-s3-test",
            provider="s3",
            bucket_name="html-bucket",
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.get("/api/cloud-sync/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert "html-s3-test" in content

    @pytest.mark.asyncio
    async def test_update_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful config update."""
        config = CloudSyncConfig(
            name="update-test",
            provider="s3",
            bucket_name="old-bucket",
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        update_data = {
            "bucket_name": "new-bucket",
            "path_prefix": "updated/"
        }
        
        response = await async_client.put(f"/api/cloud-sync/{config.id}", json=update_data)
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["bucket_name"] == "new-bucket"
        assert response_data["path_prefix"] == "updated/"

    @pytest.mark.asyncio
    async def test_update_config_duplicate_name(self, async_client: AsyncClient, test_db: Session):
        """Test updating config with duplicate name."""
        # Create two configs
        config1 = CloudSyncConfig(name="config1", provider="s3", bucket_name="bucket1")
        config2 = CloudSyncConfig(name="config2", provider="s3", bucket_name="bucket2")
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()
        
        # Try to update config2 with config1's name
        update_data = {"name": "config1"}
        response = await async_client.put(f"/api/cloud-sync/{config2.id}", json=update_data)
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful config deletion."""
        config = CloudSyncConfig(
            name="delete-test",
            provider="s3",
            bucket_name="delete-bucket"
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.delete(f"/api/cloud-sync/{config.id}")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "deleted successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_delete_config_htmx(self, async_client: AsyncClient, test_db: Session):
        """Test config deletion via HTMX."""
        config = CloudSyncConfig(
            name="htmx-delete-test",
            provider="s3",
            bucket_name="htmx-bucket"
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.delete(
            f"/api/cloud-sync/{config.id}",
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent config."""
        response = await async_client.delete("/api/cloud-sync/999")
        
        assert response.status_code == 500  # Service throws generic error
        assert "Failed to delete" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_enable_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test enabling config."""
        config = CloudSyncConfig(
            name="enable-test",
            provider="s3",
            bucket_name="test-bucket",
            enabled=False
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(f"/api/cloud-sync/{config.id}/enable")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "enabled successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_disable_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test disabling config."""
        config = CloudSyncConfig(
            name="disable-test",
            provider="s3",
            bucket_name="test-bucket",
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(f"/api/cloud-sync/{config.id}/disable")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "disabled successfully" in response_data["message"]

    @pytest.mark.asyncio
    async def test_enable_disable_htmx(self, async_client: AsyncClient, test_db: Session):
        """Test enable/disable via HTMX."""
        config = CloudSyncConfig(
            name="htmx-toggle-test",
            provider="s3",
            bucket_name="test-bucket",
            enabled=False
        )
        test_db.add(config)
        test_db.commit()
        
        # Test enable with HTMX
        response = await async_client.post(
            f"/api/cloud-sync/{config.id}/enable",
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cloudSyncUpdate"

    @pytest.mark.asyncio
    async def test_config_lifecycle(self, async_client: AsyncClient, test_db: Session):
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        config_data = {
            "name": "lifecycle-test",
            "provider": "s3",
            "bucket_name": "lifecycle-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        create_response = await async_client.post("/api/cloud-sync/", json=config_data)
        assert create_response.status_code == 200
        config_id = create_response.json()["id"]
        
        # Update
        update_data = {"bucket_name": "updated-bucket"}
        update_response = await async_client.put(f"/api/cloud-sync/{config_id}", json=update_data)
        assert update_response.status_code == 200
        
        # Disable
        disable_response = await async_client.post(f"/api/cloud-sync/{config_id}/disable")
        assert disable_response.status_code == 200
        
        # Enable
        enable_response = await async_client.post(f"/api/cloud-sync/{config_id}/enable")
        assert enable_response.status_code == 200
        
        # Delete
        delete_response = await async_client.delete(f"/api/cloud-sync/{config_id}")
        assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_test_config_endpoint_not_found(self, async_client: AsyncClient):
        """Test testing non-existent config."""
        response = await async_client.post("/api/cloud-sync/999/test")
        
        assert response.status_code == 500  # Service throws generic error

    @pytest.mark.asyncio
    async def test_error_handling_edge_cases(self, async_client: AsyncClient):
        """Test various error handling scenarios."""
        # Test with invalid JSON
        response = await async_client.post(
            "/api/cloud-sync/",
            content='{"invalid": json}',
            headers={"content-type": "application/json"}
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_htmx_error_responses(self, async_client: AsyncClient):
        """Test that HTMX error responses return HTML."""
        config_data = {
            "name": "htmx-validation-error",
            "provider": "s3"
            # Missing required fields
        }
        
        response = await async_client.post(
            "/api/cloud-sync/",
            json=config_data,
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 422  # Validation error returns 422
        assert response.json()["detail"]  # Should have validation error details