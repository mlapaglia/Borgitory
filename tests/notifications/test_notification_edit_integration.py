"""
Integration tests for notification edit functionality.
Tests the full flow from clicking edit button to rendering provider-specific forms.
"""

import pytest
from typing import Dict, Any
from unittest.mock import Mock
from fastapi.testclient import TestClient

from borgitory.main import app
from borgitory.services.notifications.config_service import NotificationConfigService


@pytest.fixture
def test_client() -> TestClient:
    """Create test client for API testing"""
    from borgitory.main import app

    return TestClient(app)


@pytest.fixture
def mock_notification_configs() -> Dict[int, Dict[str, Any]]:
    """Mock notification configurations for testing"""
    # Create mock config objects instead of real SQLAlchemy models
    telegram_config = Mock()
    telegram_config.id = 1
    telegram_config.name = "Test Telegram"
    telegram_config.provider = "telegram"
    telegram_config.enabled = True

    discord_config = Mock()
    discord_config.id = 2
    discord_config.name = "Test Discord"
    discord_config.provider = "discord"
    discord_config.enabled = True

    pushover_config = Mock()
    pushover_config.id = 3
    pushover_config.name = "Test Pushover"
    pushover_config.provider = "pushover"
    pushover_config.enabled = True

    configs = {
        1: {
            "config": telegram_config,
            "decrypted": {
                "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
                "chat_id": "@test_channel",
                "parse_mode": "HTML",
                "disable_notification": False,
            },
        },
        2: {
            "config": discord_config,
            "decrypted": {
                "webhook_url": "https://discord.com/api/webhooks/123456789/abcdefghijk",
                "username": "Borgitory",
                "avatar_url": "",
            },
        },
        3: {
            "config": pushover_config,
            "decrypted": {
                "user_key": "u123456789012345678901234567890",
                "app_token": "a123456789012345678901234567890",
                "priority": 0,
                "sound": "default",
            },
        },
    }
    return configs


class TestNotificationEditIntegration:
    """Test notification edit form integration"""

    def test_telegram_edit_form_renders_correctly(
        self,
        test_client: TestClient,
        mock_notification_configs: Dict[int, Dict[str, Any]],
    ) -> None:
        """Test that editing a Telegram notification renders the correct form"""
        # Setup mock service
        mock_service = Mock(spec=NotificationConfigService)
        config_data = mock_notification_configs[1]
        mock_service.get_config_with_decrypted_data.return_value = (
            config_data["config"],
            config_data["decrypted"],
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/1/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Verify response
        assert response.status_code == 200
        html_content = response.text

        # Check that it's the edit form
        assert "Edit Notification Configuration" in html_content
        assert 'name="name"' in html_content
        assert 'value="Test Telegram"' in html_content

        # Check provider type is shown as read-only
        assert "Provider Type" in html_content
        assert "Telegram" in html_content
        assert 'name="provider"' in html_content
        assert 'value="telegram"' in html_content

        # Check Telegram-specific fields are present
        assert "Telegram Bot Token" in html_content
        assert 'name="bot_token"' in html_content
        assert 'value="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk"' in html_content

        assert "Chat ID" in html_content
        assert 'name="chat_id"' in html_content
        assert 'value="@test_channel"' in html_content

        assert "Message Format" in html_content
        assert 'name="parse_mode"' in html_content
        assert "selected" in html_content  # HTML should be selected

        assert "Send Silent Notifications" in html_content
        assert 'name="disable_notification"' in html_content

        # Check form buttons
        assert "Update Configuration" in html_content
        assert "Cancel" in html_content
        assert 'hx-get="/api/notifications/form"' in html_content

        # Verify service was called correctly
        mock_service.get_config_with_decrypted_data.assert_called_once_with(1)

    def test_discord_edit_form_renders_correctly(
        self,
        test_client: TestClient,
        mock_notification_configs: Dict[int, Dict[str, Any]],
    ) -> None:
        """Test that editing a Discord notification renders the correct form"""
        # Setup mock service
        mock_service = Mock(spec=NotificationConfigService)
        config_data = mock_notification_configs[2]
        mock_service.get_config_with_decrypted_data.return_value = (
            config_data["config"],
            config_data["decrypted"],
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/2/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Verify response
        assert response.status_code == 200
        html_content = response.text

        # Check that it's the edit form with Discord fields
        assert "Edit Notification Configuration" in html_content
        assert 'value="Test Discord"' in html_content
        assert "Discord" in html_content

        # Check Discord-specific fields are present
        assert "Discord Webhook URL" in html_content
        assert 'name="webhook_url"' in html_content
        assert (
            'value="https://discord.com/api/webhooks/123456789/abcdefghijk"'
            in html_content
        )

        assert "Bot Username" in html_content
        assert 'name="username"' in html_content
        assert 'value="Borgitory"' in html_content

        assert "Bot Avatar URL" in html_content
        assert 'name="avatar_url"' in html_content

        # Should NOT contain Telegram or Pushover fields
        assert "Telegram Bot Token" not in html_content
        assert "Pushover User Key" not in html_content
        assert "Chat ID" not in html_content
        assert "App Token" not in html_content

    def test_pushover_edit_form_renders_correctly(
        self,
        test_client: TestClient,
        mock_notification_configs: Dict[int, Dict[str, Any]],
    ) -> None:
        """Test that editing a Pushover notification renders the correct form"""
        # Setup mock service
        mock_service = Mock(spec=NotificationConfigService)
        config_data = mock_notification_configs[3]
        mock_service.get_config_with_decrypted_data.return_value = (
            config_data["config"],
            config_data["decrypted"],
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/3/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Verify response
        assert response.status_code == 200
        html_content = response.text

        # Check that it's the edit form with Pushover fields
        assert "Edit Notification Configuration" in html_content
        assert 'value="Test Pushover"' in html_content
        assert "Pushover" in html_content

        # Check Pushover-specific fields are present
        assert "Pushover User Key" in html_content
        assert 'name="user_key"' in html_content
        assert 'value="u123456789012345678901234567890"' in html_content

        assert "App Token" in html_content
        assert 'name="app_token"' in html_content
        assert 'value="a123456789012345678901234567890"' in html_content

        assert "Default Priority" in html_content
        assert 'name="priority"' in html_content
        assert (
            'value="0"' in html_content and "selected" in html_content
        )  # Normal priority selected

        assert "Default Sound" in html_content
        assert 'name="sound"' in html_content
        assert 'value="default"' in html_content and "selected" in html_content

        # Should NOT contain Discord or Telegram fields
        assert "Discord Webhook URL" not in html_content
        assert "Telegram Bot Token" not in html_content
        assert "Chat ID" not in html_content

    def test_edit_form_handles_missing_config(self, test_client: TestClient) -> None:
        """Test that edit form handles missing configuration gracefully"""
        # Setup mock service to raise HTTPException
        mock_service = Mock(spec=NotificationConfigService)
        from fastapi import HTTPException

        mock_service.get_config_with_decrypted_data.side_effect = HTTPException(
            status_code=404, detail="Configuration not found"
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/999/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Should get 404
        assert response.status_code == 404

    def test_edit_form_includes_proper_htmx_attributes(
        self,
        test_client: TestClient,
        mock_notification_configs: Dict[int, Dict[str, Any]],
    ) -> None:
        """Test that edit form includes proper HTMX attributes for functionality"""
        # Setup mock service
        mock_service = Mock(spec=NotificationConfigService)
        config_data = mock_notification_configs[1]  # Use Telegram config
        mock_service.get_config_with_decrypted_data.return_value = (
            config_data["config"],
            config_data["decrypted"],
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/1/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Verify response
        assert response.status_code == 200
        html_content = response.text

        # Check HTMX attributes for form submission
        assert 'hx-put="/api/notifications/1"' in html_content
        assert 'hx-target="#notification-status"' in html_content

        # Check HTMX attributes for cancel button
        assert 'hx-get="/api/notifications/form"' in html_content
        assert 'hx-target="#notification-form-container"' in html_content
        assert 'hx-swap="innerHTML"' in html_content

        # Check form structure
        assert 'id="notification-edit-form"' in html_content
        assert 'id="provider-fields-container"' in html_content

    def test_edit_form_preserves_field_values(
        self,
        test_client: TestClient,
        mock_notification_configs: Dict[int, Dict[str, Any]],
    ) -> None:
        """Test that edit form preserves all field values from decrypted config"""
        # Setup mock service with custom values
        mock_service = Mock(spec=NotificationConfigService)

        custom_config = Mock()
        custom_config.id = 1
        custom_config.name = "Custom Telegram Bot"
        custom_config.provider = "telegram"
        custom_config.enabled = True

        custom_decrypted = {
            "bot_token": "987654321:ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvuts",
            "chat_id": "-123456789",
            "parse_mode": "MarkdownV2",
            "disable_notification": True,
        }

        mock_service.get_config_with_decrypted_data.return_value = (
            custom_config,
            custom_decrypted,
        )

        # Override the dependency
        from borgitory.dependencies import get_notification_config_service

        app.dependency_overrides[get_notification_config_service] = lambda: mock_service

        # Make request to edit endpoint
        response = test_client.get("/api/notifications/1/edit")

        # Clean up
        app.dependency_overrides.clear()

        # Verify response
        assert response.status_code == 200
        html_content = response.text

        # Check that custom values are preserved
        assert 'value="Custom Telegram Bot"' in html_content
        assert 'value="987654321:ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvuts"' in html_content
        assert 'value="-123456789"' in html_content
        assert 'value="MarkdownV2"' in html_content and "selected" in html_content
        assert (
            "checked" in html_content
        )  # disable_notification checkbox should be checked

    def test_unified_template_discovery(self) -> None:
        """Test that unified templates are properly discovered for all providers"""
        from borgitory.api.notifications import _get_provider_template

        # Test that all unified templates exist for both create and edit modes
        providers = ["telegram", "discord", "pushover"]
        for provider in providers:
            create_template = _get_provider_template(provider, "create")
            edit_template = _get_provider_template(provider, "edit")

            # Both should return the same unified template
            assert create_template is not None
            assert edit_template is not None
            assert create_template == edit_template  # Unified template
            assert create_template.endswith(f"{provider}_fields.html")
            assert "partials/notifications/providers/" in create_template

        # Test that non-existent provider returns None
        assert _get_provider_template("nonexistent", "edit") is None

    def test_unified_template_mode_handling(self) -> None:
        """Test that unified templates handle create/edit modes correctly via context"""
        from borgitory.api.notifications import _get_provider_template

        providers = ["telegram", "discord", "pushover"]
        for provider in providers:
            # Both modes should use the same template file
            create_template = _get_provider_template(provider, "create")
            edit_template = _get_provider_template(provider, "edit")

            assert create_template == edit_template  # Same unified template
            assert create_template is not None and create_template.endswith(
                f"{provider}_fields.html"
            )

            # The difference is in the context passed to the template (mode parameter)
            # This test verifies the template discovery works for the unified approach
