"""
Tests for cloud_sync API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import Mock, patch, AsyncMock

from app.models.database import CloudSyncConfig
from app.api.cloud_sync import CloudSyncService


class TestCloudSyncEndpoints:
    """Test class for cloud sync API endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_s3_cloud_sync_config(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test creating an S3 cloud sync configuration."""
        response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_s3_cloud_sync_config["name"]
        assert data["provider"] == "s3"
        assert data["bucket_name"] == sample_s3_cloud_sync_config["bucket_name"]
        assert "access_key" not in data  # Credentials should not be returned
    
    @pytest.mark.asyncio
    async def test_create_sftp_cloud_sync_config(self, async_client: AsyncClient, sample_sftp_cloud_sync_config):
        """Test creating an SFTP cloud sync configuration."""
        response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_sftp_cloud_sync_config
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_sftp_cloud_sync_config["name"]
        assert data["provider"] == "sftp"
        assert data["host"] == sample_sftp_cloud_sync_config["host"]
        assert data["username"] == sample_sftp_cloud_sync_config["username"]
        assert "password" not in data  # Credentials should not be returned
    
    @pytest.mark.asyncio
    async def test_create_cloud_sync_config_duplicate_name(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test creating cloud sync config with duplicate name fails."""
        # Create first config
        await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        
        # Try to create second config with same name
        response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "already exists" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_create_s3_config_missing_credentials(self, async_client: AsyncClient):
        """Test creating S3 config without credentials fails."""
        invalid_config = {
            "name": "test-s3-invalid",
            "provider": "s3",
            "bucket_name": "test-bucket"
            # Missing access_key and secret_key
        }
        
        response = await async_client.post(
            "/api/cloud-sync/",
            json=invalid_config
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    async def test_create_sftp_config_missing_fields(self, async_client: AsyncClient):
        """Test creating SFTP config without required fields fails."""
        invalid_config = {
            "name": "test-sftp-invalid",
            "provider": "sftp",
            "host": "example.com"
            # Missing username, remote_path, and credentials
        }
        
        response = await async_client.post(
            "/api/cloud-sync/",
            json=invalid_config
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    async def test_create_sftp_config_missing_credentials(self, async_client: AsyncClient):
        """Test creating SFTP config without credentials fails."""
        invalid_config = {
            "name": "test-sftp-invalid",
            "provider": "sftp",
            "host": "example.com",
            "username": "testuser",
            "remote_path": "/backup"
            # Missing password and private_key
        }
        
        response = await async_client.post(
            "/api/cloud-sync/",
            json=invalid_config
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    @pytest.mark.asyncio
    async def test_create_unsupported_provider(self, async_client: AsyncClient):
        """Test creating config with unsupported provider fails."""
        invalid_config = {
            "name": "test-invalid",
            "provider": "dropbox"  # Unsupported
        }
        
        response = await async_client.post(
            "/api/cloud-sync/",
            json=invalid_config
        )
        
        assert response.status_code == 422  # FastAPI validation error for invalid provider
    
    @pytest.mark.asyncio
    async def test_list_cloud_sync_configs_empty(self, async_client: AsyncClient):
        """Test listing cloud sync configurations when none exist."""
        response = await async_client.get("/api/cloud-sync/")
        
        assert response.status_code == 200
        data = response.json()
        assert data == []
    
    @pytest.mark.asyncio
    async def test_list_cloud_sync_configs_with_data(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test listing cloud sync configurations with existing data."""
        # Create a config first
        await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        
        response = await async_client.get("/api/cloud-sync/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == sample_s3_cloud_sync_config["name"]
    
    @pytest.mark.asyncio
    async def test_get_cloud_sync_config_by_id(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test getting a specific cloud sync configuration by ID."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        response = await async_client.get(f"/api/cloud-sync/{config_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == config_id
        assert data["name"] == sample_s3_cloud_sync_config["name"]
    
    @pytest.mark.asyncio
    async def test_get_cloud_sync_config_not_found(self, async_client: AsyncClient):
        """Test getting non-existent cloud sync configuration."""
        response = await async_client.get("/api/cloud-sync/999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cloud sync configuration not found"
    
    @pytest.mark.asyncio
    async def test_update_cloud_sync_config(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test updating a cloud sync configuration."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        # Update the config
        update_data = {
            "name": "updated-s3-config",
            "path_prefix": "updated-path/"
        }
        
        response = await async_client.put(f"/api/cloud-sync/{config_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "updated-s3-config"
        assert data["path_prefix"] == "updated-path/"
    
    @pytest.mark.asyncio
    async def test_update_cloud_sync_config_not_found(self, async_client: AsyncClient):
        """Test updating non-existent cloud sync configuration."""
        update_data = {"name": "non-existent"}
        
        response = await async_client.put("/api/cloud-sync/999", json=update_data)
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cloud sync configuration not found"
    
    @pytest.mark.asyncio
    async def test_delete_cloud_sync_config(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test deleting a cloud sync configuration."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        # Delete the config
        response = await async_client.delete(f"/api/cloud-sync/{config_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "deleted successfully" in data["message"]
        
        # Verify it's gone
        get_response = await async_client.get(f"/api/cloud-sync/{config_id}")
        assert get_response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_cloud_sync_config_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent cloud sync configuration."""
        response = await async_client.delete("/api/cloud-sync/999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cloud sync configuration not found"
    
    @pytest.mark.asyncio
    async def test_enable_cloud_sync_config(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test enabling a cloud sync configuration."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        # Enable the config
        response = await async_client.post(f"/api/cloud-sync/{config_id}/enable")
        
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data["message"]
    
    @pytest.mark.asyncio
    async def test_disable_cloud_sync_config(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test disabling a cloud sync configuration."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        # Disable the config
        response = await async_client.post(f"/api/cloud-sync/{config_id}/disable")
        
        assert response.status_code == 200
        data = response.json()
        assert "disabled" in data["message"]
    
    @pytest.mark.asyncio
    async def test_test_s3_cloud_sync_config_success(self, async_client: AsyncClient, sample_s3_cloud_sync_config, mock_rclone_service):
        """Test testing S3 cloud sync configuration with success."""
        # Create a config first
        create_response = await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        config_id = create_response.json()["id"]
        
        # Mock successful S3 test
        mock_rclone_service.test_s3_connection = AsyncMock(return_value={
            "status": "success",
            "message": "Connection successful"
        })
        
        with patch('app.api.cloud_sync.rclone_service', mock_rclone_service):
            response = await async_client.post(f"/api/cloud-sync/{config_id}/test")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Successfully connected" in data["message"]
    
    @pytest.mark.asyncio
    async def test_test_cloud_sync_config_not_found(self, async_client: AsyncClient):
        """Test testing non-existent cloud sync configuration."""
        response = await async_client.post("/api/cloud-sync/999/test")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cloud sync configuration not found"
    
    @pytest.mark.asyncio
    async def test_get_cloud_sync_configs_html_empty(self, async_client: AsyncClient):
        """Test HTML endpoint with no configurations."""
        response = await async_client.get("/api/cloud-sync/html")
        
        assert response.status_code == 200
        assert "no cloud sync" in response.text.lower()
    
    @pytest.mark.asyncio
    async def test_get_cloud_sync_configs_html_with_data(self, async_client: AsyncClient, sample_s3_cloud_sync_config):
        """Test HTML endpoint with configurations."""
        # Create a config first
        await async_client.post(
            "/api/cloud-sync/",
            json=sample_s3_cloud_sync_config
        )
        
        response = await async_client.get("/api/cloud-sync/html")
        
        assert response.status_code == 200
        # The HTML template may not exist in test environment, so just check it doesn't error


class TestCloudSyncService:
    """Test class for CloudSyncService."""
    
    def test_create_s3_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config):
        """Test CloudSyncService.create_cloud_sync_config with S3 provider."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        result = service.create_cloud_sync_config(config_data)
        
        assert result.name == sample_s3_cloud_sync_config["name"]
        assert result.provider == "s3"
        assert result.bucket_name == sample_s3_cloud_sync_config["bucket_name"]
    
    def test_create_sftp_cloud_sync_config(self, test_db, sample_sftp_cloud_sync_config):
        """Test CloudSyncService.create_cloud_sync_config with SFTP provider."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_sftp_cloud_sync_config)
        
        result = service.create_cloud_sync_config(config_data)
        
        assert result.name == sample_sftp_cloud_sync_config["name"]
        assert result.provider == "sftp"
        assert result.host == sample_sftp_cloud_sync_config["host"]
        assert result.username == sample_sftp_cloud_sync_config["username"]
    
    def test_create_cloud_sync_config_duplicate_name(self, test_db, sample_s3_cloud_sync_config):
        """Test creating config with duplicate name fails."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create first config
        service.create_cloud_sync_config(config_data)
        
        # Try to create second config with same name
        with pytest.raises(Exception) as exc_info:
            service.create_cloud_sync_config(config_data)
        
        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)
    
    def test_get_cloud_sync_configs_empty(self, test_db):
        """Test getting cloud sync configs when none exist."""
        service = CloudSyncService(test_db)
        
        result = service.get_cloud_sync_configs()
        
        assert result == []
    
    def test_get_cloud_sync_configs_with_data(self, test_db, sample_s3_cloud_sync_config):
        """Test getting cloud sync configs with existing data."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create a config first
        service.create_cloud_sync_config(config_data)
        
        # Get all configs
        result = service.get_cloud_sync_configs()
        
        assert len(result) == 1
        assert result[0].name == sample_s3_cloud_sync_config["name"]
    
    def test_get_cloud_sync_config_by_id_success(self, test_db, sample_s3_cloud_sync_config):
        """Test getting cloud sync config by ID when it exists."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create a config first
        created_config = service.create_cloud_sync_config(config_data)
        
        # Get by ID
        result = service.get_cloud_sync_config_by_id(created_config.id)
        
        assert result.id == created_config.id
        assert result.name == sample_s3_cloud_sync_config["name"]
    
    def test_get_cloud_sync_config_by_id_not_found(self, test_db):
        """Test getting cloud sync config by ID when it doesn't exist."""
        service = CloudSyncService(test_db)
        
        with pytest.raises(Exception) as exc_info:
            service.get_cloud_sync_config_by_id(999)
        
        assert exc_info.value.status_code == 404
        assert "Cloud sync configuration not found" in str(exc_info.value.detail)
    
    def test_enable_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config):
        """Test enabling a cloud sync configuration."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create config first
        created_config = service.create_cloud_sync_config(config_data)
        
        # Enable it
        result = service.enable_cloud_sync_config(created_config.id)
        
        assert result.enabled is True
    
    def test_disable_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config):
        """Test disabling a cloud sync configuration."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create config first
        created_config = service.create_cloud_sync_config(config_data)
        
        # Disable it
        result = service.disable_cloud_sync_config(created_config.id)
        
        assert result.enabled is False
    
    def test_delete_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config):
        """Test deleting a cloud sync configuration."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create config first
        created_config = service.create_cloud_sync_config(config_data)
        config_id = created_config.id
        
        # Delete it
        service.delete_cloud_sync_config(config_id)
        
        # Verify it's gone
        with pytest.raises(Exception) as exc_info:
            service.get_cloud_sync_config_by_id(config_id)
        
        assert exc_info.value.status_code == 404
    
    def test_update_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config):
        """Test updating a cloud sync configuration."""
        from app.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create config first
        created_config = service.create_cloud_sync_config(config_data)
        
        # Update it
        update_data = CloudSyncConfigUpdate(
            name="updated-s3-config",
            path_prefix="updated-path/"
        )
        result = service.update_cloud_sync_config(created_config.id, update_data)
        
        assert result.name == "updated-s3-config"
        assert result.path_prefix == "updated-path/"
    
    @pytest.mark.asyncio
    async def test_test_s3_cloud_sync_config(self, test_db, sample_s3_cloud_sync_config, mock_rclone_service):
        """Test testing S3 cloud sync configuration."""
        from app.models.schemas import CloudSyncConfigCreate
        
        service = CloudSyncService(test_db)
        config_data = CloudSyncConfigCreate(**sample_s3_cloud_sync_config)
        
        # Create config first
        created_config = service.create_cloud_sync_config(config_data)
        
        # Mock successful S3 test
        mock_rclone_service.test_s3_connection = AsyncMock(return_value={
            "status": "success",
            "message": "Connection successful"
        })
        
        # Test the config
        result = await service.test_cloud_sync_config(created_config.id, mock_rclone_service)
        
        assert result["status"] == "success"
        mock_rclone_service.test_s3_connection.assert_called_once()


@pytest.fixture
def sample_s3_cloud_sync_config():
    """Sample S3 cloud sync configuration for testing."""
    return {
        "name": "test-s3-config",
        "provider": "s3",
        "bucket_name": "test-bucket",
        "path_prefix": "backups/",
        "access_key": "AKIAIOSFODNN7EXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    }


@pytest.fixture
def sample_sftp_cloud_sync_config():
    """Sample SFTP cloud sync configuration for testing."""
    return {
        "name": "test-sftp-config",
        "provider": "sftp",
        "host": "example.com",
        "port": 22,
        "username": "testuser",
        "remote_path": "/backup",
        "password": "testpassword"
    }