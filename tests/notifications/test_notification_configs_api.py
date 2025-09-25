"""
Tests for notification API endpoints - HTMX response format testing only
Business logic tests are in test_notification_config_service.py
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from borgitory.models.database import NotificationConfig
from borgitory.services.notifications.registry import NotificationProviderRegistry


def create_pushover_notification_config(
    name: str, enabled: bool = True
) -> NotificationConfig:
    """Create a test Pushover notification configuration."""
    config = NotificationConfig()
    config.name = name
    config.provider = "pushover"
    config.enabled = enabled

    # Use valid 30-character keys for Pushover validation
    config.provider_config = (
        '{"user_key": "u' + "x" * 29 + '", "app_token": "a' + "x" * 29 + '"}'
    )

    return config


class TestNotificationConfigsAPIHTMX:
    """Test class for notification API HTMX responses."""

    def test_get_supported_providers(
        self, notification_registry: NotificationProviderRegistry
    ) -> None:
        """Test getting supported providers from registry directly."""
        provider_info = notification_registry.get_all_provider_info()

        assert isinstance(provider_info, dict)
        assert len(provider_info) > 0

        # Should include pushover provider
        assert "pushover" in provider_info
        pushover_info = provider_info["pushover"]
        assert pushover_info.label == "Pushover"
        assert hasattr(pushover_info, "description")

    @pytest.mark.asyncio
    async def test_get_provider_fields_pushover(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting provider fields for Pushover returns HTML."""
        response = await async_client.get(
            "/api/notifications/provider-fields?provider=pushover"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert len(content) > 0
        assert "user_key" in content  # Should contain pushover-specific fields

    @pytest.mark.asyncio
    async def test_get_provider_fields_discord(self, async_client: AsyncClient) -> None:
        """Test getting provider fields for Discord returns HTML."""
        response = await async_client.get(
            "/api/notifications/provider-fields?provider=discord"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_provider_fields_no_provider(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting provider fields without provider returns empty."""
        response = await async_client.get("/api/notifications/provider-fields")

        assert response.status_code == 200
        assert response.text == ""

    @pytest.mark.asyncio
    async def test_get_provider_fields_unknown_provider(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting provider fields for unknown provider returns error message."""
        response = await async_client.get(
            "/api/notifications/provider-fields?provider=unknown"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "No template found" in response.text

    @pytest.mark.asyncio
    async def test_create_config_html_response(self, async_client: AsyncClient) -> None:
        """Test config creation returns HTML response."""
        form_data = {
            "name": "test-pushover-create",
            "provider": "pushover",
            "user_key": "u" + "x" * 29,  # 30 character user key
            "app_token": "a" + "x" * 29,  # 30 character app token
        }

        response = await async_client.post("/api/notifications/", data=form_data)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_create_config_validation_error(
        self, async_client: AsyncClient
    ) -> None:
        """Test config creation with invalid data returns error HTML."""
        form_data = {
            "name": "test-invalid",
            "provider": "pushover",
            "user_key": "short",  # Too short for validation
            "app_token": "short",  # Too short for validation
        }

        response = await async_client.post("/api/notifications/", data=form_data)

        assert response.status_code == 400  # Proper HTTP status for validation error
        # Should contain error message in response
        content = response.text
        assert (
            "error" in content.lower()
            or "invalid" in content.lower()
            or "validation" in content.lower()
        )

    @pytest.mark.asyncio
    async def test_enable_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config enable returns HTML response."""
        config = create_pushover_notification_config(
            name="enable-html-test", enabled=False
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        response = await async_client.post(f"/api/notifications/{config.id}/enable")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_disable_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config disable returns HTML response."""
        config = create_pushover_notification_config(
            name="disable-html-test", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        response = await async_client.post(f"/api/notifications/{config.id}/disable")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_test_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config test returns HTML response."""
        config = create_pushover_notification_config(
            name="test-config-html", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        # Mock the notification service test
        with patch(
            "borgitory.services.notifications.config_service.NotificationConfigService.test_config_with_service"
        ) as mock_test:
            mock_test.return_value = (True, "Connection successful")

            response = await async_client.post(f"/api/notifications/{config.id}/test")

            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_edit_form_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting edit form returns HTML."""
        config = create_pushover_notification_config(
            name="edit-form-test", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        response = await async_client.get(f"/api/notifications/{config.id}/edit")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert len(content) > 0
        assert config.name in content

    @pytest.mark.asyncio
    async def test_update_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config update returns HTML response."""
        config = create_pushover_notification_config(
            name="update-html-test", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        form_data = {
            "name": "updated-name",
            "provider": "pushover",
            "user_key": "u" + "x" * 29,  # 30 character user key
            "app_token": "a" + "x" * 29,  # 30 character app token
        }

        response = await async_client.put(
            f"/api/notifications/{config.id}", data=form_data
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_delete_config_html_response(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test config deletion returns HTML response."""
        config = create_pushover_notification_config(
            name="delete-html-test", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        response = await async_client.delete(f"/api/notifications/{config.id}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_get_notification_form_html_response(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting notification form returns HTML."""
        response = await async_client.get("/api/notifications/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert len(content) > 0
        assert "notification" in content.lower()

    @pytest.mark.asyncio
    async def test_config_not_found_responses(self, async_client: AsyncClient) -> None:
        """Test various endpoints with non-existent config ID."""
        non_existent_id = 99999

        # Test enable
        response = await async_client.post(
            f"/api/notifications/{non_existent_id}/enable"
        )
        assert response.status_code == 404  # Proper HTTP status for not found
        assert "not found" in response.text.lower() or "error" in response.text.lower()

        # Test disable
        response = await async_client.post(
            f"/api/notifications/{non_existent_id}/disable"
        )
        assert response.status_code == 404  # Proper HTTP status for not found
        assert "not found" in response.text.lower() or "error" in response.text.lower()

        # Test delete
        response = await async_client.delete(f"/api/notifications/{non_existent_id}")
        assert response.status_code == 404  # Proper HTTP status for not found
        assert "not found" in response.text.lower() or "error" in response.text.lower()

        # Test test
        response = await async_client.post(f"/api/notifications/{non_existent_id}/test")
        assert response.status_code == 404  # Proper HTTP status for not found
        assert "not found" in response.text.lower() or "error" in response.text.lower()

        # Test edit form
        response = await async_client.get(f"/api/notifications/{non_existent_id}/edit")
        assert (
            response.status_code == 404 or response.status_code == 500
        )  # Either is acceptable
        assert "not found" in response.text.lower() or "error" in response.text.lower()

        # Test update (may return 400 due to form validation before config lookup)
        response = await async_client.put(
            f"/api/notifications/{non_existent_id}", data={"name": "test"}
        )
        assert (
            response.status_code == 400 or response.status_code == 404
        )  # Either is acceptable
        assert (
            "not found" in response.text.lower()
            or "error" in response.text.lower()
            or "invalid" in response.text.lower()
        )
