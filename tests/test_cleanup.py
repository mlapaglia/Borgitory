"""
Tests for cleanup API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import Mock, patch

from app.models.database import CleanupConfig
from app.api.cleanup import CleanupService


class TestCleanupEndpoints:
    """Test class for cleanup API endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_cleanup_config_simple_strategy(self, async_client: AsyncClient, sample_simple_cleanup_config):
        """Test creating a simple cleanup configuration."""
        response = await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_simple_cleanup_config["name"]
        assert data["strategy"] == "simple"
        assert data["keep_within_days"] == 30
        assert data["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_create_cleanup_config_advanced_strategy(self, async_client: AsyncClient, sample_advanced_cleanup_config):
        """Test creating an advanced cleanup configuration."""
        response = await async_client.post(
            "/api/cleanup/",
            json=sample_advanced_cleanup_config
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_advanced_cleanup_config["name"]
        assert data["strategy"] == "advanced"
        assert data["keep_daily"] == 7
        assert data["keep_weekly"] == 4
        assert data["keep_monthly"] == 6
        assert data["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_create_cleanup_config_simple_missing_days(self, async_client: AsyncClient):
        """Test creating simple strategy without keep_within_days fails."""
        invalid_config = {
            "name": "invalid-simple",
            "strategy": "simple"
            # Missing keep_within_days
        }
        
        response = await async_client.post(
            "/api/cleanup/",
            json=invalid_config
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Simple strategy requires keep_within_days" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_create_cleanup_config_advanced_no_retention(self, async_client: AsyncClient):
        """Test creating advanced strategy without any retention parameters fails."""
        invalid_config = {
            "name": "invalid-advanced",
            "strategy": "advanced"
            # Missing all keep_* parameters
        }
        
        response = await async_client.post(
            "/api/cleanup/",
            json=invalid_config
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Advanced strategy requires at least one keep_* parameter" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_list_cleanup_configs_empty(self, async_client: AsyncClient):
        """Test listing cleanup configurations when none exist."""        
        response = await async_client.get("/api/cleanup/")
        
        assert response.status_code == 200
        data = response.json()
        assert data == []
    
    @pytest.mark.asyncio
    async def test_list_cleanup_configs_with_data(self, async_client: AsyncClient, test_db, sample_simple_cleanup_config):
        """Test listing cleanup configurations with existing data."""
        # Create a cleanup config first
        await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        
        response = await async_client.get("/api/cleanup/")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == sample_simple_cleanup_config["name"]
    
    @pytest.mark.asyncio
    async def test_list_cleanup_configs_pagination(self, async_client: AsyncClient, test_db):
        """Test cleanup config list pagination."""
        # Create multiple configs
        for i in range(5):
            config = {
                "name": f"test-config-{i}",
                "strategy": "simple",
                "keep_within_days": 30
            }
            await async_client.post("/api/cleanup/", json=config)
        
        # Test pagination
        response = await async_client.get("/api/cleanup/?skip=2&limit=2")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
    
    @pytest.mark.asyncio
    async def test_enable_cleanup_config(self, async_client: AsyncClient, test_db, sample_simple_cleanup_config):
        """Test enabling a cleanup configuration."""
        # Create and get the config ID
        create_response = await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        config_id = create_response.json()["id"]
        
        # Disable it first
        await async_client.post(f"/api/cleanup/{config_id}/disable")
        
        # Then enable it
        response = await async_client.post(f"/api/cleanup/{config_id}/enable")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Cleanup configuration enabled successfully"
        
        # Verify it's enabled
        list_response = await async_client.get("/api/cleanup/")
        configs = list_response.json()
        assert configs[0]["enabled"] is True
    
    @pytest.mark.asyncio
    async def test_disable_cleanup_config(self, async_client: AsyncClient, test_db, sample_simple_cleanup_config):
        """Test disabling a cleanup configuration."""
        # Create and get the config ID
        create_response = await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        config_id = create_response.json()["id"]
        
        # Disable it
        response = await async_client.post(f"/api/cleanup/{config_id}/disable")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Cleanup configuration disabled successfully"
        
        # Verify it's disabled
        list_response = await async_client.get("/api/cleanup/")
        configs = list_response.json()
        assert configs[0]["enabled"] is False
    
    @pytest.mark.asyncio
    async def test_delete_cleanup_config(self, async_client: AsyncClient, test_db, sample_simple_cleanup_config):
        """Test deleting a cleanup configuration."""
        # Create and get the config ID
        create_response = await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        config_id = create_response.json()["id"]
        
        # Delete it
        response = await async_client.delete(f"/api/cleanup/{config_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Cleanup configuration deleted successfully"
        
        # Verify it's gone
        list_response = await async_client.get("/api/cleanup/")
        configs = list_response.json()
        assert len(configs) == 0
    
    @pytest.mark.asyncio
    async def test_enable_nonexistent_config(self, async_client: AsyncClient):
        """Test enabling a non-existent cleanup configuration."""
        response = await async_client.post("/api/cleanup/999/enable")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cleanup configuration not found"
    
    @pytest.mark.asyncio
    async def test_disable_nonexistent_config(self, async_client: AsyncClient):
        """Test disabling a non-existent cleanup configuration."""
        response = await async_client.post("/api/cleanup/999/disable")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cleanup configuration not found"
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_config(self, async_client: AsyncClient):
        """Test deleting a non-existent cleanup configuration."""
        response = await async_client.delete("/api/cleanup/999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Cleanup configuration not found"
    
    @pytest.mark.asyncio
    async def test_get_cleanup_configs_html_empty(self, async_client: AsyncClient):
        """Test HTML endpoint with no configurations."""
        response = await async_client.get("/api/cleanup/html")
        
        assert response.status_code == 200
        assert "No cleanup policies configured" in response.text
    
    @pytest.mark.asyncio
    async def test_get_cleanup_configs_html_with_data(self, async_client: AsyncClient, test_db, sample_simple_cleanup_config):
        """Test HTML endpoint with configurations."""
        # Create a cleanup config first
        await async_client.post(
            "/api/cleanup/",
            json=sample_simple_cleanup_config
        )
        
        response = await async_client.get("/api/cleanup/html")
        
        assert response.status_code == 200
        assert sample_simple_cleanup_config["name"] in response.text
        assert "Keep archives within 30 days" in response.text
        assert "Enabled" in response.text


class TestCleanupService:
    """Test class for CleanupService."""
    
    def test_create_simple_cleanup_config(self, test_db, sample_simple_cleanup_config):
        """Test CleanupService.create_cleanup_config with simple strategy."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        result = service.create_cleanup_config(config_data)
        
        assert result.name == sample_simple_cleanup_config["name"]
        assert result.strategy == "simple"
        assert result.keep_within_days == 30
        assert result.enabled is True
    
    def test_create_advanced_cleanup_config(self, test_db, sample_advanced_cleanup_config):
        """Test CleanupService.create_cleanup_config with advanced strategy."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_advanced_cleanup_config)
        
        result = service.create_cleanup_config(config_data)
        
        assert result.name == sample_advanced_cleanup_config["name"]
        assert result.strategy == "advanced"
        assert result.keep_daily == 7
        assert result.keep_weekly == 4
        assert result.keep_monthly == 6
        assert result.enabled is True
    
    def test_get_cleanup_configs_empty(self, test_db):
        """Test getting cleanup configs when none exist."""
        service = CleanupService(test_db)
        
        result = service.get_cleanup_configs()
        
        assert result == []
    
    def test_get_cleanup_configs_with_data(self, test_db, sample_simple_cleanup_config):
        """Test getting cleanup configs with existing data."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        # Create a config first
        service.create_cleanup_config(config_data)
        
        # Get all configs
        result = service.get_cleanup_configs()
        
        assert len(result) == 1
        assert result[0].name == sample_simple_cleanup_config["name"]
    
    def test_get_cleanup_config_by_id_success(self, test_db, sample_simple_cleanup_config):
        """Test getting cleanup config by ID when it exists."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        # Create a config first
        created_config = service.create_cleanup_config(config_data)
        
        # Get by ID
        result = service.get_cleanup_config_by_id(created_config.id)
        
        assert result.id == created_config.id
        assert result.name == sample_simple_cleanup_config["name"]
    
    def test_get_cleanup_config_by_id_not_found(self, test_db):
        """Test getting cleanup config by ID when it doesn't exist."""
        service = CleanupService(test_db)
        
        with pytest.raises(Exception) as exc_info:
            service.get_cleanup_config_by_id(999)
        
        assert exc_info.value.status_code == 404
        assert "Cleanup configuration not found" in str(exc_info.value.detail)
    
    def test_enable_cleanup_config(self, test_db, sample_simple_cleanup_config):
        """Test enabling a cleanup configuration."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        # Create and disable config first
        created_config = service.create_cleanup_config(config_data)
        service.disable_cleanup_config(created_config.id)
        
        # Enable it
        result = service.enable_cleanup_config(created_config.id)
        
        assert result.enabled is True
    
    def test_disable_cleanup_config(self, test_db, sample_simple_cleanup_config):
        """Test disabling a cleanup configuration."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        # Create config first
        created_config = service.create_cleanup_config(config_data)
        
        # Disable it
        result = service.disable_cleanup_config(created_config.id)
        
        assert result.enabled is False
    
    def test_delete_cleanup_config(self, test_db, sample_simple_cleanup_config):
        """Test deleting a cleanup configuration."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        config_data = CleanupConfigCreate(**sample_simple_cleanup_config)
        
        # Create config first
        created_config = service.create_cleanup_config(config_data)
        config_id = created_config.id
        
        # Delete it
        service.delete_cleanup_config(config_id)
        
        # Verify it's gone
        with pytest.raises(Exception) as exc_info:
            service.get_cleanup_config_by_id(config_id)
        
        assert exc_info.value.status_code == 404
    
    def test_validate_simple_strategy_missing_days(self, test_db):
        """Test validation fails for simple strategy without keep_within_days."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        invalid_config = CleanupConfigCreate(
            name="invalid-simple",
            strategy="simple"
            # Missing keep_within_days
        )
        
        with pytest.raises(Exception) as exc_info:
            service.create_cleanup_config(invalid_config)
        
        assert exc_info.value.status_code == 400
        assert "Simple strategy requires keep_within_days" in str(exc_info.value.detail)
    
    def test_validate_advanced_strategy_no_retention(self, test_db):
        """Test validation fails for advanced strategy without retention parameters."""
        from app.models.schemas import CleanupConfigCreate
        
        service = CleanupService(test_db)
        invalid_config = CleanupConfigCreate(
            name="invalid-advanced",
            strategy="advanced"
            # Missing all keep_* parameters
        )
        
        with pytest.raises(Exception) as exc_info:
            service.create_cleanup_config(invalid_config)
        
        assert exc_info.value.status_code == 400
        assert "Advanced strategy requires at least one keep_* parameter" in str(exc_info.value.detail)


@pytest.fixture
def sample_simple_cleanup_config():
    """Sample simple cleanup configuration for testing."""
    return {
        "name": "test-simple-cleanup",
        "strategy": "simple",
        "keep_within_days": 30,
        "show_list": True,
        "show_stats": False,
        "save_space": True
    }


@pytest.fixture
def sample_advanced_cleanup_config():
    """Sample advanced cleanup configuration for testing."""
    return {
        "name": "test-advanced-cleanup",
        "strategy": "advanced",
        "keep_daily": 7,
        "keep_weekly": 4,
        "keep_monthly": 6,
        "keep_yearly": 1,
        "show_list": True,
        "show_stats": True,
        "save_space": False
    }