"""
Tests for notification configs API endpoints - HTMX and response validation focused
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from fastapi.responses import HTMLResponse

from models.schemas import NotificationConfigCreate


@pytest.fixture
def mock_request():
    """Mock FastAPI request"""
    request = MagicMock(spec=Request)
    request.headers = {}
    return request


@pytest.fixture
def mock_templates():
    """Mock templates dependency"""
    templates = MagicMock()
    mock_response = MagicMock(spec=HTMLResponse)
    mock_response.headers = {}
    templates.TemplateResponse.return_value = mock_response
    templates.get_template.return_value.render.return_value = "mocked html content"
    return templates


@pytest.fixture
def mock_service():
    """Mock NotificationConfigService"""
    service = MagicMock()
    return service


@pytest.fixture
def mock_pushover_service():
    """Mock PushoverService"""
    pushover_service = AsyncMock()
    return pushover_service


@pytest.fixture
def sample_config_create():
    """Sample config creation data"""
    return NotificationConfigCreate(
        name="test-config",
        provider="pushover",
        notify_on_success=True,
        notify_on_failure=False,
        user_key="test-user",
        app_token="test-token",
    )


class TestNotificationConfigsAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    @pytest.mark.asyncio
    async def test_create_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ):
        """Test successful config creation returns correct HTMX response."""
        from api.notifications import create_notification_config

        # Mock successful service response
        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.create_config.return_value = (True, mock_config, None)

        result = await create_notification_config(
            mock_request, mock_templates, sample_config_create, mock_service
        )

        # Verify service was called with correct parameters
        mock_service.create_config.assert_called_once_with(
            name=sample_config_create.name,
            provider=sample_config_create.provider,
            notify_on_success=sample_config_create.notify_on_success,
            notify_on_failure=sample_config_create.notify_on_failure,
            user_key=sample_config_create.user_key,
            app_token=sample_config_create.app_token,
        )

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/create_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_create_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ):
        """Test failed config creation returns correct HTMX error response."""
        from api.notifications import create_notification_config

        # Mock service failure
        mock_service.create_config.return_value = (
            False,
            None,
            "Failed to create notification configuration",
        )

        await create_notification_config(
            mock_request, mock_templates, sample_config_create, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/create_error.html",
            {"error_message": "Failed to create notification configuration"},
            status_code=500,
        )

    def test_list_configs_success(self, mock_service):
        """Test listing configs returns service result."""
        from api.notifications import list_notification_configs

        mock_configs = [MagicMock(), MagicMock()]
        mock_service.get_all_configs.return_value = mock_configs

        result = list_notification_configs(mock_service, skip=0, limit=100)

        # Verify service was called with correct parameters
        mock_service.get_all_configs.assert_called_once_with(skip=0, limit=100)

        # Verify result is returned
        assert result == mock_configs

    def test_get_configs_html_success(self, mock_request, mock_templates, mock_service):
        """Test getting configs HTML returns correct template response."""
        from api.notifications import get_notification_configs_html

        mock_configs_data = [
            {"name": "config1", "notification_desc": "Success, Failures"},
            {"name": "config2", "notification_desc": "Failures"},
        ]
        mock_service.get_configs_with_descriptions.return_value = mock_configs_data

        get_notification_configs_html(mock_request, mock_templates, mock_service)

        # Verify service was called
        mock_service.get_configs_with_descriptions.assert_called_once()

        # Verify template was rendered
        mock_templates.get_template.assert_called_once_with(
            "partials/notifications/config_list_content.html"
        )

    def test_get_configs_html_exception(
        self, mock_request, mock_templates, mock_service
    ):
        """Test getting configs HTML with exception returns error template."""
        from api.notifications import get_notification_configs_html

        mock_service.get_configs_with_descriptions.side_effect = Exception(
            "Service error"
        )

        get_notification_configs_html(mock_request, mock_templates, mock_service)

        # Verify error template response
        mock_templates.get_template.assert_called_with("partials/jobs/error_state.html")

    @pytest.mark.asyncio
    async def test_test_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, mock_pushover_service
    ):
        """Test successful config test returns correct HTMX response."""
        from api.notifications import test_notification_config

        # Mock successful service response
        mock_service.get_config_credentials.return_value = (
            True,
            "test-user",
            "test-token",
            None,
        )
        mock_pushover_service.test_pushover_connection.return_value = {
            "status": "success",
            "message": "Test successful",
        }

        await test_notification_config(
            mock_request, 1, mock_pushover_service, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.get_config_credentials.assert_called_once_with(1)

        # Verify pushover service was called
        mock_pushover_service.test_pushover_connection.assert_called_once_with(
            "test-user", "test-token"
        )

        # Verify success template response
        mock_templates.TemplateResponse.assert_called_with(
            mock_request,
            "partials/notifications/test_success.html",
            {"message": "Test successful"},
        )

    @pytest.mark.asyncio
    async def test_test_config_not_found_htmx_response(
        self, mock_request, mock_templates, mock_service, mock_pushover_service
    ):
        """Test testing non-existent config returns correct HTMX error response."""
        from api.notifications import test_notification_config

        # Mock service failure
        mock_service.get_config_credentials.return_value = (
            False,
            None,
            None,
            "Notification configuration not found",
        )

        await test_notification_config(
            mock_request, 999, mock_pushover_service, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_with(
            mock_request,
            "partials/notifications/test_error.html",
            {"error_message": "Notification configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_test_config_pushover_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, mock_pushover_service
    ):
        """Test failed pushover test returns correct HTMX error response."""
        from api.notifications import test_notification_config

        # Mock successful credential retrieval but failed test
        mock_service.get_config_credentials.return_value = (
            True,
            "test-user",
            "test-token",
            None,
        )
        mock_pushover_service.test_pushover_connection.return_value = {
            "status": "error",
            "message": "Invalid credentials",
        }

        await test_notification_config(
            mock_request, 1, mock_pushover_service, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_with(
            mock_request,
            "partials/notifications/test_error.html",
            {"error_message": "Invalid credentials"},
            status_code=400,
        )

    @pytest.mark.asyncio
    async def test_enable_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test successful config enable returns correct HTMX response."""
        from api.notifications import enable_notification_config

        mock_service.enable_config.return_value = (
            True,
            "Config enabled successfully!",
            None,
        )

        result = await enable_notification_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.enable_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/action_success.html",
            {"message": "Config enabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_enable_config_not_found_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test enabling non-existent config returns correct HTMX error response."""
        from api.notifications import enable_notification_config

        mock_service.enable_config.return_value = (
            False,
            None,
            "Notification configuration not found",
        )

        await enable_notification_config(
            mock_request, 999, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/action_error.html",
            {"error_message": "Notification configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_disable_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test successful config disable returns correct HTMX response."""
        from api.notifications import disable_notification_config

        mock_service.disable_config.return_value = (
            True,
            "Config disabled successfully!",
            None,
        )

        result = await disable_notification_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.disable_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/action_success.html",
            {"message": "Config disabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_get_edit_form_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test getting edit form returns correct HTMX template response."""
        from api.notifications import get_notification_config_edit_form

        mock_config = MagicMock()
        mock_service.get_config_by_id.return_value = mock_config
        mock_service.get_config_credentials.return_value = (
            True,
            "test-user",
            "test-token",
            None,
        )

        await get_notification_config_edit_form(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.get_config_by_id.assert_called_once_with(1)
        mock_service.get_config_credentials.assert_called_once_with(1)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/edit_form.html",
            {
                "config": mock_config,
                "user_key": "test-user",
                "app_token": "test-token",
                "is_edit_mode": True,
            },
        )

    @pytest.mark.asyncio
    async def test_get_edit_form_not_found(
        self, mock_request, mock_templates, mock_service
    ):
        """Test getting edit form for non-existent config raises HTTPException."""
        from api.notifications import get_notification_config_edit_form
        from fastapi import HTTPException

        mock_service.get_config_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_notification_config_edit_form(
                mock_request, 999, mock_templates, mock_service
            )

        assert exc_info.value.status_code == 404
        assert "Notification configuration not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ):
        """Test successful config update returns correct HTMX response."""
        from api.notifications import update_notification_config

        mock_config = MagicMock()
        mock_config.name = "updated-config"
        mock_service.update_config.return_value = (True, mock_config, None)

        result = await update_notification_config(
            mock_request, 1, sample_config_create, mock_templates, mock_service
        )

        # Verify service was called with correct parameters
        mock_service.update_config.assert_called_once_with(
            config_id=1,
            name=sample_config_create.name,
            provider=sample_config_create.provider,
            notify_on_success=sample_config_create.notify_on_success,
            notify_on_failure=sample_config_create.notify_on_failure,
            user_key=sample_config_create.user_key,
            app_token=sample_config_create.app_token,
        )

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/update_success.html",
            {"config_name": "updated-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_update_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ):
        """Test failed config update returns correct HTMX error response."""
        from api.notifications import update_notification_config

        mock_service.update_config.return_value = (
            False,
            None,
            "Notification configuration not found",
        )

        await update_notification_config(
            mock_request, 999, sample_config_create, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/update_error.html",
            {"error_message": "Notification configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_get_notification_form_htmx_response(
        self, mock_request, mock_templates
    ):
        """Test getting notification form returns correct HTMX template response."""
        from api.notifications import get_notification_form

        await get_notification_form(mock_request, mock_templates)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/add_form.html",
            {},
        )

    @pytest.mark.asyncio
    async def test_delete_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test successful config deletion returns correct HTMX response."""
        from api.notifications import delete_notification_config

        mock_service.delete_config.return_value = (True, "test-config", None)

        result = await delete_notification_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.delete_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/action_success.html",
            {
                "message": "Notification configuration 'test-config' deleted successfully!"
            },
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "notificationUpdate"

    @pytest.mark.asyncio
    async def test_delete_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service
    ):
        """Test failed config deletion returns correct HTMX error response."""
        from api.notifications import delete_notification_config

        mock_service.delete_config.return_value = (
            False,
            None,
            "Notification configuration not found",
        )

        await delete_notification_config(
            mock_request, 999, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/notifications/action_error.html",
            {"error_message": "Notification configuration not found"},
            status_code=404,
        )
