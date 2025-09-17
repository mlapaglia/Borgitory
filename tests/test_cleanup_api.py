"""
Tests for cleanup API endpoints - HTMX and response validation focused
"""

import pytest
from unittest.mock import MagicMock
from fastapi import Request
from fastapi.responses import HTMLResponse

from borgitory.models.schemas import CleanupConfigCreate, CleanupConfigUpdate


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
    """Mock CleanupService"""
    service = MagicMock()
    return service


@pytest.fixture
def sample_config_create():
    """Sample config creation data"""
    return CleanupConfigCreate(
        name="test-config", strategy="simple", keep_within_days=30
    )


@pytest.fixture
def sample_config_update():
    """Sample config update data"""
    return CleanupConfigUpdate(name="updated-config", keep_within_days=60)


class TestCleanupAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    @pytest.mark.asyncio
    async def test_get_cleanup_form_success(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting cleanup form returns correct template response."""
        from borgitory.api.cleanup import get_cleanup_form

        mock_form_data = {"repositories": []}
        mock_service.get_form_data.return_value = mock_form_data

        await get_cleanup_form(mock_request, mock_templates, mock_service)

        # Verify service was called
        mock_service.get_form_data.assert_called_once()

        # Verify template was rendered
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/config_form.html",
            mock_form_data,
        )

    @pytest.mark.asyncio
    async def test_get_policy_form_success(self, mock_request, mock_templates) -> None:
        """Test getting policy form returns correct template response."""
        from borgitory.api.cleanup import get_policy_form

        await get_policy_form(mock_request, mock_templates)

        # Verify template was rendered
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/create_form.html",
            {},
        )

    @pytest.mark.asyncio
    async def test_get_strategy_fields_success(
        self, mock_request, mock_templates
    ) -> None:
        """Test getting strategy fields returns correct template response."""
        from borgitory.api.cleanup import get_strategy_fields

        await get_strategy_fields(mock_request, mock_templates, strategy="advanced")

        # Verify template was rendered
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/strategy_fields.html",
            {"strategy": "advanced"},
        )

    @pytest.mark.asyncio
    async def test_create_cleanup_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ) -> None:
        """Test successful config creation returns correct HTMX response."""
        from borgitory.api.cleanup import create_cleanup_config

        # Mock successful service response
        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.create_cleanup_config.return_value = (True, mock_config, None)

        result = await create_cleanup_config(
            mock_request, sample_config_create, mock_templates, mock_service
        )

        # Verify service was called with correct parameters
        mock_service.create_cleanup_config.assert_called_once_with(sample_config_create)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/create_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_create_cleanup_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ) -> None:
        """Test failed config creation returns correct HTMX error response."""
        from borgitory.api.cleanup import create_cleanup_config

        # Mock service failure
        mock_service.create_cleanup_config.return_value = (
            False,
            None,
            "Failed to create cleanup configuration",
        )

        await create_cleanup_config(
            mock_request, sample_config_create, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/create_error.html",
            {"error_message": "Failed to create cleanup configuration"},
            status_code=400,
        )

    def test_list_cleanup_configs_success(self, mock_service) -> None:
        """Test listing configs returns service result."""
        from borgitory.api.cleanup import list_cleanup_configs

        mock_configs = [MagicMock(), MagicMock()]
        mock_service.get_cleanup_configs.return_value = mock_configs

        result = list_cleanup_configs(mock_service, skip=0, limit=100)

        # Verify service was called with correct parameters
        mock_service.get_cleanup_configs.assert_called_once_with(0, 100)

        # Verify result is returned
        assert result == mock_configs

    def test_get_cleanup_configs_html_success(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting configs HTML returns correct template response."""
        from borgitory.api.cleanup import get_cleanup_configs_html

        mock_configs_data = [
            {"name": "config1", "description": "Keep archives within 30 days"},
            {"name": "config2", "description": "7 daily, 4 weekly"},
        ]
        mock_service.get_configs_with_descriptions.return_value = mock_configs_data

        get_cleanup_configs_html(mock_request, mock_templates, mock_service)

        # Verify service was called
        mock_service.get_configs_with_descriptions.assert_called_once()

        # Verify template was rendered
        mock_templates.get_template.assert_called_once_with(
            "partials/prune/config_list_content.html"
        )

    def test_get_cleanup_configs_html_exception(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting configs HTML with exception returns error template."""
        from borgitory.api.cleanup import get_cleanup_configs_html

        mock_service.get_configs_with_descriptions.side_effect = Exception(
            "Service error"
        )

        get_cleanup_configs_html(mock_request, mock_templates, mock_service)

        # Verify error template response
        mock_templates.get_template.assert_called_with("partials/jobs/error_state.html")

    @pytest.mark.asyncio
    async def test_enable_cleanup_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config enable returns correct HTMX response."""
        from borgitory.api.cleanup import enable_cleanup_config

        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.enable_cleanup_config.return_value = (True, mock_config, None)

        result = await enable_cleanup_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.enable_cleanup_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Prune policy 'test-config' enabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_enable_cleanup_config_not_found_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test enabling non-existent config returns correct HTMX error response."""
        from borgitory.api.cleanup import enable_cleanup_config

        mock_service.enable_cleanup_config.return_value = (
            False,
            None,
            "Cleanup configuration not found",
        )

        await enable_cleanup_config(mock_request, 999, mock_templates, mock_service)

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Cleanup configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_disable_cleanup_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config disable returns correct HTMX response."""
        from borgitory.api.cleanup import disable_cleanup_config

        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.disable_cleanup_config.return_value = (True, mock_config, None)

        result = await disable_cleanup_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.disable_cleanup_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Prune policy 'test-config' disabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_disable_cleanup_config_not_found_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test disabling non-existent config returns correct HTMX error response."""
        from borgitory.api.cleanup import disable_cleanup_config

        mock_service.disable_cleanup_config.return_value = (
            False,
            None,
            "Cleanup configuration not found",
        )

        await disable_cleanup_config(mock_request, 999, mock_templates, mock_service)

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Cleanup configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_get_cleanup_config_edit_form_success(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting edit form returns correct template response."""
        from borgitory.api.cleanup import get_cleanup_config_edit_form

        mock_config = MagicMock()
        mock_service.get_cleanup_config_by_id.return_value = mock_config

        await get_cleanup_config_edit_form(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.get_cleanup_config_by_id.assert_called_once_with(1)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/edit_form.html",
            {
                "config": mock_config,
                "is_edit_mode": True,
            },
        )

    @pytest.mark.asyncio
    async def test_get_cleanup_config_edit_form_not_found(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting edit form for non-existent config raises HTTPException."""
        from borgitory.api.cleanup import get_cleanup_config_edit_form
        from fastapi import HTTPException

        mock_service.get_cleanup_config_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_cleanup_config_edit_form(
                mock_request, 999, mock_templates, mock_service
            )

        assert exc_info.value.status_code == 404
        assert "Cleanup configuration not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_cleanup_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_update
    ) -> None:
        """Test successful config update returns correct HTMX response."""
        from borgitory.api.cleanup import update_cleanup_config

        mock_config = MagicMock()
        mock_config.name = "updated-config"
        mock_service.update_cleanup_config.return_value = (True, mock_config, None)

        result = await update_cleanup_config(
            mock_request, 1, sample_config_update, mock_templates, mock_service
        )

        # Verify service was called with correct parameters
        mock_service.update_cleanup_config.assert_called_once_with(
            1, sample_config_update
        )

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/update_success.html",
            {"config_name": "updated-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_update_cleanup_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_update
    ) -> None:
        """Test failed config update returns correct HTMX error response."""
        from borgitory.api.cleanup import update_cleanup_config

        mock_service.update_cleanup_config.return_value = (
            False,
            None,
            "Cleanup configuration not found",
        )

        await update_cleanup_config(
            mock_request, 999, sample_config_update, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/update_error.html",
            {"error_message": "Cleanup configuration not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_delete_cleanup_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config deletion returns correct HTMX response."""
        from borgitory.api.cleanup import delete_cleanup_config

        mock_service.delete_cleanup_config.return_value = (True, "test-config", None)

        result = await delete_cleanup_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.delete_cleanup_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Cleanup configuration 'test-config' deleted successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "cleanupConfigUpdate"

    @pytest.mark.asyncio
    async def test_delete_cleanup_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test failed config deletion returns correct HTMX error response."""
        from borgitory.api.cleanup import delete_cleanup_config

        mock_service.delete_cleanup_config.return_value = (
            False,
            None,
            "Cleanup configuration not found",
        )

        await delete_cleanup_config(mock_request, 999, mock_templates, mock_service)

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Cleanup configuration not found"},
            status_code=404,
        )
