"""
Tests for notifications API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock

from app.models.database import NotificationConfig


class TestNotificationsAPI:
    """Test class for notifications API endpoints."""

    @pytest.mark.asyncio
    async def test_create_pushover_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful Pushover config creation."""
        config_data = {
            "name": "test-pushover",
            "provider": "pushover",
            "user_key": "test-user-key",
            "app_token": "test-app-token",
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        
        response = await async_client.post("/api/notifications/", json=config_data)
        
        assert response.status_code == 201
        response_data = response.json()
        assert response_data["name"] == "test-pushover"
        assert response_data["provider"] == "pushover"
        assert response_data["notify_on_success"] is True
        assert response_data["notify_on_failure"] is True
        assert response_data["enabled"] is True
        # Credentials should not be returned in response
        assert "user_key" not in response_data
        assert "app_token" not in response_data

    @pytest.mark.asyncio
    async def test_create_pushover_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful Pushover config creation via HTMX."""
        config_data = {
            "name": "test-pushover-htmx",
            "provider": "pushover",
            "user_key": "test-user-key",
            "app_token": "test-app-token",
            "notify_on_success": True,
            "notify_on_failure": False,
        }
        
        response = await async_client.post(
            "/api/notifications/",
            json=config_data,
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"
        
        # Verify config was created in database
        config = test_db.query(NotificationConfig).filter(
            NotificationConfig.name == "test-pushover-htmx"
        ).first()
        assert config is not None
        assert config.provider == "pushover"

    @pytest.mark.asyncio
    async def test_create_config_missing_credentials(self, async_client: AsyncClient):
        """Test config creation with missing credentials."""
        config_data = {
            "name": "incomplete-pushover",
            "provider": "pushover",
            "notify_on_success": True,
            "notify_on_failure": True,
            # Missing user_key and app_token
        }
        
        response = await async_client.post("/api/notifications/", json=config_data)
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_config_invalid_provider(self, async_client: AsyncClient):
        """Test config creation with invalid provider."""
        config_data = {
            "name": "invalid-provider",
            "provider": "invalid_provider",
            "user_key": "test-key",
            "app_token": "test-token",
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        
        response = await async_client.post("/api/notifications/", json=config_data)
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_config_database_error(self, async_client: AsyncClient):
        """Test config creation with database error."""
        config_data = {
            "name": "db-error-test",
            "provider": "pushover",
            "user_key": "test-user-key",
            "app_token": "test-app-token",
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        
        with patch('app.models.database.NotificationConfig.set_pushover_credentials', 
                   side_effect=Exception("Database error")):
            response = await async_client.post("/api/notifications/", json=config_data)
            
            assert response.status_code == 500
            assert "Failed to create notification configuration" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_config_htmx_database_error(self, async_client: AsyncClient):
        """Test config creation HTMX error handling."""
        config_data = {
            "name": "htmx-db-error-test",
            "provider": "pushover",
            "user_key": "test-user-key",
            "app_token": "test-app-token",
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        
        with patch('app.models.database.NotificationConfig.set_pushover_credentials',
                   side_effect=Exception("Database error")):
            response = await async_client.post(
                "/api/notifications/",
                json=config_data,
                headers={"hx-request": "true"}
            )
            
            assert response.status_code == 500
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_list_notification_configs_empty(self, async_client: AsyncClient):
        """Test listing notification configs when empty."""
        response = await async_client.get("/api/notifications/")
        
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_notification_configs_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test listing notification configs with data."""
        # Create test configs
        config1 = NotificationConfig(
            name="pushover-1",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config1.set_pushover_credentials("user1", "token1")
        
        config2 = NotificationConfig(
            name="pushover-2",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=True,
            enabled=False
        )
        config2.set_pushover_credentials("user2", "token2")
        
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()
        
        response = await async_client.get("/api/notifications/")
        
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2
        assert response_data[0]["name"] == "pushover-1"
        assert response_data[1]["name"] == "pushover-2"

    @pytest.mark.asyncio
    async def test_list_notification_configs_pagination(self, async_client: AsyncClient, test_db: Session):
        """Test listing notification configs with pagination."""
        # Create multiple configs
        for i in range(5):
            config = NotificationConfig(
                name=f"pushover-{i}",
                provider="pushover",
                notify_on_success=True,
                notify_on_failure=True,
                enabled=True
            )
            config.set_pushover_credentials(f"user{i}", f"token{i}")
            test_db.add(config)
        test_db.commit()
        
        # Test with limit
        response = await async_client.get("/api/notifications/?skip=1&limit=2")
        
        assert response.status_code == 200
        response_data = response.json()
        assert len(response_data) == 2

    @pytest.mark.asyncio
    async def test_get_notification_configs_html_empty(self, async_client: AsyncClient):
        """Test getting notification configs as HTML when empty."""
        response = await async_client.get("/api/notifications/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_notification_configs_html_with_data(self, async_client: AsyncClient, test_db: Session):
        """Test getting notification configs as HTML with data."""
        config = NotificationConfig(
            name="html-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.get("/api/notifications/html")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_notification_configs_html_success_failure_flags(self, async_client: AsyncClient, test_db: Session):
        """Test HTML view shows correct notification descriptions."""
        # Config that notifies on both success and failure
        config1 = NotificationConfig(
            name="both-notifications",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config1.set_pushover_credentials("user1", "token1")
        
        # Config that only notifies on failure
        config2 = NotificationConfig(
            name="failure-only",
            provider="pushover", 
            notify_on_success=False,
            notify_on_failure=True,
            enabled=True
        )
        config2.set_pushover_credentials("user2", "token2")
        
        # Config that doesn't notify on anything
        config3 = NotificationConfig(
            name="no-notifications",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=False,
            enabled=True
        )
        config3.set_pushover_credentials("user3", "token3")
        
        test_db.add_all([config1, config2, config3])
        test_db.commit()
        
        response = await async_client.get("/api/notifications/html")
        
        assert response.status_code == 200
        # The template should show notification descriptions based on flags

    @pytest.mark.asyncio
    async def test_get_notification_configs_html_error_handling(self, async_client: AsyncClient):
        """Test HTML endpoint error handling."""
        with patch('sqlalchemy.orm.Query.all', side_effect=Exception("Database error")):
            response = await async_client.get("/api/notifications/html")
            
            assert response.status_code == 200  # Returns error template
            content = response.text
            assert "Error loading notification configurations" in content

    @pytest.mark.asyncio
    async def test_test_pushover_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful Pushover config testing."""
        config = NotificationConfig(
            name="test-config",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        # Override the dependency directly in the FastAPI app
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.return_value = {"status": "success", "message": "Connection successful"}
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            response = await async_client.post(f"/api/notifications/{config.id}/test")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["status"] == "success"
            mock_pushover.test_pushover_connection.assert_called_once()
        finally:
            # Clean up the override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_test_pushover_config_failure(self, async_client: AsyncClient, test_db: Session):
        """Test Pushover config test failure."""
        config = NotificationConfig(
            name="test-config-fail",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("invalid-user", "invalid-token")
        test_db.add(config)
        test_db.commit()
        
        # Override the dependency directly in the FastAPI app
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.return_value = {"status": "error", "message": "Invalid credentials"}
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            response = await async_client.post(f"/api/notifications/{config.id}/test")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["status"] == "error"
        finally:
            # Clean up the override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_test_config_not_found(self, async_client: AsyncClient):
        """Test testing non-existent config."""
        response = await async_client.post("/api/notifications/999/test")
        
        assert response.status_code == 500  # API catches HTTPException and converts to 500
        assert "Notification configuration not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_test_unsupported_provider(self, async_client: AsyncClient, test_db: Session):
        """Test testing config with unsupported provider."""
        # Create a config with an unsupported provider (this shouldn't happen normally)
        config = NotificationConfig(
            name="unsupported-config",
            provider="unsupported",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(f"/api/notifications/{config.id}/test")
        
        assert response.status_code == 500  # API catches HTTPException and converts to 500
        assert "Unsupported notification provider" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_test_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test successful config testing via HTMX."""
        config = NotificationConfig(
            name="htmx-test-config",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        # Override the dependency directly in the FastAPI app
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.return_value = {"status": "success", "message": "Test successful"}
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            response = await async_client.post(
                f"/api/notifications/{config.id}/test",
                headers={"hx-request": "true"}
            )
            
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
        finally:
            # Clean up the override
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_test_config_htmx_error(self, async_client: AsyncClient, test_db: Session):
        """Test config testing error via HTMX."""
        config = NotificationConfig(
            name="htmx-test-error",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("bad-user", "bad-token")
        test_db.add(config)
        test_db.commit()
        
        # Override the dependency directly in the FastAPI app
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.return_value = {"status": "error", "message": "Test failed"}
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            response = await async_client.post(
                f"/api/notifications/{config.id}/test",
                headers={"hx-request": "true"}
            )
            
            assert response.status_code == 400
        finally:
            # Clean up the override
            app.dependency_overrides.clear()
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_enable_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test enabling notification config."""
        config = NotificationConfig(
            name="enable-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=False  # Start disabled
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(f"/api/notifications/{config.id}/enable")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "enabled successfully" in response_data["message"]
        
        # Verify config was enabled in database
        test_db.refresh(config)
        assert config.enabled is True

    @pytest.mark.asyncio
    async def test_enable_config_not_found(self, async_client: AsyncClient):
        """Test enabling non-existent config."""
        response = await async_client.post("/api/notifications/999/enable")
        
        assert response.status_code == 500  # API catches HTTPException and converts to 500
        assert "Notification configuration not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_enable_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test enabling config via HTMX."""
        config = NotificationConfig(
            name="htmx-enable-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=False
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(
            f"/api/notifications/{config.id}/enable",
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_enable_config_database_error(self, async_client: AsyncClient, test_db: Session):
        """Test enable config with database error."""
        config = NotificationConfig(
            name="db-error-enable",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=False
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        with patch.object(test_db, 'commit', side_effect=Exception("Database error")):
            response = await async_client.post(f"/api/notifications/{config.id}/enable")
            
            assert response.status_code == 500
            assert "Failed to enable notification" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_disable_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test disabling notification config."""
        config = NotificationConfig(
            name="disable-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True  # Start enabled
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.post(f"/api/notifications/{config.id}/disable")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "disabled successfully" in response_data["message"]
        
        # Verify config was disabled in database
        test_db.refresh(config)
        assert config.enabled is False

    @pytest.mark.asyncio
    async def test_disable_config_not_found(self, async_client: AsyncClient):
        """Test disabling non-existent config."""
        response = await async_client.post("/api/notifications/999/disable")
        
        assert response.status_code == 500  # API catches HTTPException and converts to 500

    @pytest.mark.asyncio
    async def test_delete_config_success(self, async_client: AsyncClient, test_db: Session):
        """Test deleting notification config."""
        config = NotificationConfig(
            name="delete-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        config_id = config.id
        
        response = await async_client.delete(f"/api/notifications/{config_id}")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "deleted successfully" in response_data["message"]
        
        # Verify config was deleted from database
        deleted_config = test_db.query(NotificationConfig).filter(
            NotificationConfig.id == config_id
        ).first()
        assert deleted_config is None

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, async_client: AsyncClient):
        """Test deleting non-existent config."""
        response = await async_client.delete("/api/notifications/999")
        
        assert response.status_code == 500  # API catches HTTPException and converts to 500

    @pytest.mark.asyncio
    async def test_delete_config_htmx_success(self, async_client: AsyncClient, test_db: Session):
        """Test deleting config via HTMX."""
        config = NotificationConfig(
            name="htmx-delete-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        response = await async_client.delete(
            f"/api/notifications/{config.id}",
            headers={"hx-request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_config_lifecycle(self, async_client: AsyncClient, test_db: Session):
        """Test complete notification config lifecycle: create, enable, disable, delete."""
        # Create
        config_data = {
            "name": "lifecycle-test",
            "provider": "pushover",
            "user_key": "test-user-key",
            "app_token": "test-app-token",
            "notify_on_success": True,
            "notify_on_failure": True,
        }
        
        create_response = await async_client.post("/api/notifications/", json=config_data)
        assert create_response.status_code == 201
        config_id = create_response.json()["id"]
        
        # Disable (it starts enabled)
        disable_response = await async_client.post(f"/api/notifications/{config_id}/disable")
        assert disable_response.status_code == 200
        
        # Enable
        enable_response = await async_client.post(f"/api/notifications/{config_id}/enable")
        assert enable_response.status_code == 200
        
        # Test (with mocked service)
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.return_value = {"status": "success", "message": "Test successful"}
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            test_response = await async_client.post(f"/api/notifications/{config_id}/test")
            assert test_response.status_code == 200
        finally:
            # Clean up only the pushover service override
            if get_pushover_service in app.dependency_overrides:
                del app.dependency_overrides[get_pushover_service]
        
        # Delete
        delete_response = await async_client.delete(f"/api/notifications/{config_id}")
        assert delete_response.status_code == 200

    @pytest.mark.asyncio
    async def test_test_config_exception_handling(self, async_client: AsyncClient, test_db: Session):
        """Test config testing with service exception."""
        config = NotificationConfig(
            name="exception-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True
        )
        config.set_pushover_credentials("test-user", "test-token")
        test_db.add(config)
        test_db.commit()
        
        # Override the dependency directly in the FastAPI app
        from app.main import app
        from app.dependencies import get_pushover_service
        mock_pushover = AsyncMock()
        mock_pushover.test_pushover_connection.side_effect = Exception("Service unavailable")
        
        app.dependency_overrides[get_pushover_service] = lambda: mock_pushover
        
        try:
            response = await async_client.post(f"/api/notifications/{config.id}/test")
            
            assert response.status_code == 500
            assert "Service unavailable" in response.json()["detail"]
        finally:
            # Clean up the override
            app.dependency_overrides.clear()