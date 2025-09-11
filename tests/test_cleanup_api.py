"""
Tests for cleanup API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.database import Repository, CleanupConfig


class TestCleanupAPI:
    """Test class for cleanup API endpoints."""

    @pytest.mark.asyncio
    async def test_get_cleanup_form(self, async_client: AsyncClient, test_db: Session):
        """Test getting cleanup configuration form."""
        # Create test repository
        repository = Repository(
            name="test-repo",
            path="/tmp/test-repo",
        )
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()
        
        response = await async_client.get("/api/cleanup/form")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        content = response.text
        assert "test-repo" in content

    @pytest.mark.asyncio
    async def test_get_cleanup_form_empty_database(self, async_client: AsyncClient, test_db: Session):
        """Test getting cleanup form when no repositories exist."""
        response = await async_client.get("/api/cleanup/form")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_strategy_fields_simple(self, async_client: AsyncClient):
        """Test getting strategy fields for simple strategy."""
        response = await async_client.get("/api/cleanup/strategy-fields?strategy=simple")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # The response should contain strategy-specific fields
        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_strategy_fields_advanced(self, async_client: AsyncClient):
        """Test getting strategy fields for advanced strategy."""
        response = await async_client.get("/api/cleanup/strategy-fields?strategy=advanced")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_strategy_fields_default(self, async_client: AsyncClient):
        """Test getting strategy fields with default strategy."""
        response = await async_client.get("/api/cleanup/strategy-fields")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_cleanup_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful cleanup config creation via API."""
        config_data = {
            "name": "test-cleanup",
            "strategy": "simple",
            "keep_within_days": 30,
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        response = await async_client.post("/api/cleanup/", json=config_data)
        
        assert response.status_code == 201
        response_data = response.json()
        assert response_data["name"] == "test-cleanup"
        assert response_data["strategy"] == "simple"
        assert response_data["keep_within_days"] == 30

    @pytest.mark.asyncio
    async def test_create_cleanup_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful cleanup config creation via HTMX."""
        config_data = {
            "name": "test-cleanup-htmx",
            "strategy": "simple",
            "keep_within_days": 30,
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        response = await async_client.post(
            "/api/cleanup/", 
            json=config_data,
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200  # HTMX responses return 200 with HTML
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_create_cleanup_config_validation_error(self, async_client: AsyncClient):
        """Test cleanup config creation with validation error."""
        config_data = {
            "name": "test-cleanup",
            "strategy": "simple",
            # Missing keep_within_days
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        response = await async_client.post("/api/cleanup/", json=config_data)
        
        assert response.status_code == 400
        assert "Simple strategy requires keep_within_days" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_cleanup_config_advanced_success(self, async_client: AsyncClient, test_db: Session):
        """Test creating advanced strategy cleanup config."""
        config_data = {
            "name": "advanced-cleanup",
            "strategy": "advanced",
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_yearly": 1,
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        response = await async_client.post("/api/cleanup/", json=config_data)
        
        assert response.status_code == 201
        response_data = response.json()
        assert response_data["name"] == "advanced-cleanup"
        assert response_data["strategy"] == "advanced"
        assert response_data["keep_daily"] == 7

    @pytest.mark.asyncio
    async def test_create_cleanup_config_advanced_validation_error(self, async_client: AsyncClient):
        """Test advanced strategy cleanup config without retention rules."""
        config_data = {
            "name": "bad-advanced-cleanup",
            "strategy": "advanced",
            # Missing all keep_* parameters
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        response = await async_client.post("/api/cleanup/", json=config_data)
        
        assert response.status_code == 400
        assert "Advanced strategy requires at least one keep_* parameter" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_cleanup_configs_empty(self, async_client: AsyncClient):
        """Test listing cleanup configurations when empty."""
        response = await async_client.get("/api/cleanup/")
        
        assert response.status_code == 200
        response_data = response.json()
        assert isinstance(response_data, list)
        assert len(response_data) == 0

    @pytest.mark.asyncio
    async def test_list_cleanup_configs_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test listing cleanup configurations with data."""
        # Create test configs
        config1 = CleanupConfig(
            name="config-1",
            strategy="simple",
            keep_within_days=30,
            enabled=True
        )
        config2 = CleanupConfig(
            name="config-2",
            strategy="advanced",
            keep_daily=7,
            enabled=False
        )
        
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()
        
        response = await async_client.get("/api/cleanup/")
        
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "config-1"
        assert response_data[1]["name"] == "config-2"

    @pytest.mark.asyncio
    async def test_list_cleanup_configs_with_pagination(self, async_client: AsyncClient):
        """Test listing cleanup configurations with pagination."""
        response = await async_client.get("/api/cleanup/?skip=10&limit=5")
        
        assert response.status_code == 200
        # Should return empty list since no data
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_cleanup_configs_html_empty(self, async_client: AsyncClient):
        """Test getting cleanup configs as HTML when empty."""
        response = await async_client.get("/api/cleanup/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_cleanup_configs_html_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test getting cleanup configs as HTML with data."""
        # Create test configs
        config = CleanupConfig(
            name="html-test-config",
            strategy="simple",
            keep_within_days=30,
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.get("/api/cleanup/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        content = response.text
        # Should contain the config name
        assert "html-test-config" in content

    @pytest.mark.asyncio
    async def test_enable_disable_delete_config_lifecycle(self, async_client: AsyncClient, test_db: Session):
        """Test complete lifecycle: create, enable, disable, delete."""
        # First create a config
        config_data = {
            "name": "lifecycle-test",
            "strategy": "simple",
            "keep_within_days": 15,
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        create_response = await async_client.post("/api/cleanup/", json=config_data)
        assert create_response.status_code == 201
        
        config_id = create_response.json()["id"]
        
        # Test enable
        enable_response = await async_client.post(f"/api/cleanup/{config_id}/enable")
        assert enable_response.status_code == 200
        assert "enabled successfully" in enable_response.json()["message"]
        
        # Test disable
        disable_response = await async_client.post(f"/api/cleanup/{config_id}/disable")
        assert disable_response.status_code == 200
        assert "disabled successfully" in disable_response.json()["message"]
        
        # Test delete
        delete_response = await async_client.delete(f"/api/cleanup/{config_id}")
        assert delete_response.status_code == 200
        assert "deleted successfully" in delete_response.json()["message"]

    @pytest.mark.asyncio
    async def test_enable_config_not_found(self, async_client: AsyncClient):
        """Test enabling non-existent config."""
        response = await async_client.post("/api/cleanup/999/enable")
        
        assert response.status_code == 500  # Service throws generic error
        assert "Failed to enable cleanup configuration" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_disable_config_not_found(self, async_client: AsyncClient):
        """Test disabling non-existent config."""
        response = await async_client.post("/api/cleanup/999/disable")
        
        assert response.status_code == 500  # Service throws generic error
        assert "Failed to disable cleanup configuration" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent config."""
        response = await async_client.delete("/api/cleanup/999")
        
        assert response.status_code == 404  # Not found error
        assert "Cleanup configuration not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_htmx_responses_have_correct_headers(self, async_client: AsyncClient, test_db: Session):
        """Test that HTMX requests return proper response headers."""
        # Create a config first
        config = CleanupConfig(
            name="htmx-test",
            strategy="simple",
            keep_within_days=30,
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        # Test enable with HTMX
        response = await async_client.post(
            f"/api/cleanup/{config.id}/enable",
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_create_duplicate_name(self, async_client: AsyncClient, test_db: Session):
        """Test creating cleanup config with duplicate name."""
        # Create first config
        config_data = {
            "name": "duplicate-test",
            "strategy": "simple",
            "keep_within_days": 30,
            "show_list": True,
            "show_stats": True,
            "save_space": False
        }
        
        first_response = await async_client.post("/api/cleanup/", json=config_data)
        assert first_response.status_code == 201
        
        # Try to create duplicate (should succeed as there's no unique constraint in the model)
        second_response = await async_client.post("/api/cleanup/", json=config_data)
        assert second_response.status_code == 201  # Model allows duplicates