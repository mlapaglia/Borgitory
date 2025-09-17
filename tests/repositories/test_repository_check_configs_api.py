"""
Tests for repository_check_configs API endpoints - HTMX and response validation focused
"""

import pytest
from unittest.mock import MagicMock
from fastapi import Request
from fastapi.responses import HTMLResponse

from borgitory.models.schemas import (
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
)


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
    return templates


@pytest.fixture
def mock_service():
    """Mock RepositoryCheckConfigService"""
    service = MagicMock()
    return service


@pytest.fixture
def sample_config_create():
    """Sample config creation data"""
    return RepositoryCheckConfigCreate(
        name="test-config",
        description="Test configuration",
        check_type="full",
        verify_data=True,
        repair_mode=False,
        save_space=False,
    )


@pytest.fixture
def sample_config_update():
    """Sample config update data"""
    return RepositoryCheckConfigUpdate(
        name="updated-config",
        description="Updated configuration",
        check_type="repository_only",
    )


class TestRepositoryCheckConfigsAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    @pytest.mark.asyncio
    async def test_create_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ) -> None:
        """Test successful config creation returns correct HTMX response."""
        from borgitory.api.repository_check_configs import (
            create_repository_check_config,
        )

        # Mock successful service response
        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.create_config.return_value = (True, mock_config, None)

        result = await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service
        )

        # Verify service was called with correct parameters
        mock_service.create_config.assert_called_once_with(
            name=sample_config_create.name,
            description=sample_config_create.description,
            check_type=sample_config_create.check_type,
            verify_data=sample_config_create.verify_data,
            repair_mode=sample_config_create.repair_mode,
            save_space=sample_config_create.save_space,
            max_duration=sample_config_create.max_duration,
            archive_prefix=sample_config_create.archive_prefix,
            archive_glob=sample_config_create.archive_glob,
            first_n_archives=sample_config_create.first_n_archives,
            last_n_archives=sample_config_create.last_n_archives,
        )

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/create_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_create_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ) -> None:
        """Test failed config creation returns correct HTMX error response."""
        from borgitory.api.repository_check_configs import (
            create_repository_check_config,
        )

        # Mock service failure
        mock_service.create_config.return_value = (
            False,
            None,
            "Config name already exists",
        )

        await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/create_error.html",
            {"error_message": "Config name already exists"},
            status_code=400,
        )

    @pytest.mark.asyncio
    async def test_create_config_server_error_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_create
    ) -> None:
        """Test server error during creation returns correct status code."""
        from borgitory.api.repository_check_configs import (
            create_repository_check_config,
        )

        # Mock service failure with "Failed to" error
        mock_service.create_config.return_value = (
            False,
            None,
            "Failed to create config",
        )

        await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service
        )

        # Verify error template response with 500 status
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/create_error.html",
            {"error_message": "Failed to create config"},
            status_code=500,
        )

    def test_get_configs_html_success(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting configs HTML returns correct template response."""
        from borgitory.api.repository_check_configs import (
            get_repository_check_configs_html,
        )

        mock_configs = [MagicMock(), MagicMock()]
        mock_service.get_all_configs.return_value = mock_configs

        get_repository_check_configs_html(mock_request, mock_templates, mock_service)

        # Verify service was called
        mock_service.get_all_configs.assert_called_once()

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/config_list_content.html",
            {"configs": mock_configs},
        )

    def test_get_configs_html_exception(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting configs HTML with exception returns error template."""
        from borgitory.api.repository_check_configs import (
            get_repository_check_configs_html,
        )

        mock_service.get_all_configs.side_effect = Exception("Service error")

        get_repository_check_configs_html(mock_request, mock_templates, mock_service)

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/common/error_message.html",
            {"error_message": "Error loading check policies: Service error"},
        )

    @pytest.mark.asyncio
    async def test_get_form_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting form returns correct HTMX template response."""
        from borgitory.api.repository_check_configs import get_repository_check_form

        mock_form_data = {"repositories": [MagicMock()], "check_configs": [MagicMock()]}
        mock_service.get_form_data.return_value = mock_form_data

        await get_repository_check_form(mock_request, mock_templates, mock_service)

        # Verify service was called
        mock_service.get_form_data.assert_called_once()

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/form.html",
            mock_form_data,
        )

    @pytest.mark.asyncio
    async def test_get_policy_form_htmx_response(
        self, mock_request, mock_templates
    ) -> None:
        """Test getting policy form returns correct HTMX template response."""
        from borgitory.api.repository_check_configs import get_policy_form

        await get_policy_form(mock_request, mock_templates)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/create_form.html",
            {},
        )

    @pytest.mark.asyncio
    async def test_get_config_edit_form_success(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting edit form returns correct HTMX template response."""
        from borgitory.api.repository_check_configs import (
            get_repository_check_config_edit_form,
        )

        mock_config = MagicMock()
        mock_service.get_config_by_id.return_value = mock_config

        await get_repository_check_config_edit_form(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.get_config_by_id.assert_called_once_with(1)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/edit_form.html",
            {"config": mock_config, "is_edit_mode": True},
        )

    @pytest.mark.asyncio
    async def test_get_config_edit_form_not_found(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test getting edit form for non-existent config raises HTTPException."""
        from borgitory.api.repository_check_configs import (
            get_repository_check_config_edit_form,
        )
        from fastapi import HTTPException

        mock_service.get_config_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_repository_check_config_edit_form(
                mock_request, 999, mock_templates, mock_service
            )

        assert exc_info.value.status_code == 404
        assert "Check policy not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_update
    ) -> None:
        """Test successful config update returns correct HTMX response."""
        from borgitory.api.repository_check_configs import (
            update_repository_check_config,
        )

        mock_config = MagicMock()
        mock_config.name = "updated-config"
        mock_service.update_config.return_value = (True, mock_config, None)

        result = await update_repository_check_config(
            mock_request, 1, sample_config_update, mock_templates, mock_service
        )

        # Verify service was called with correct parameters
        update_dict = sample_config_update.model_dump(exclude_unset=True)
        mock_service.update_config.assert_called_once_with(1, update_dict)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/update_success.html",
            {"config_name": "updated-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_update_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service, sample_config_update
    ) -> None:
        """Test failed config update returns correct HTMX error response."""
        from borgitory.api.repository_check_configs import (
            update_repository_check_config,
        )

        mock_service.update_config.return_value = (False, None, "Config not found")

        await update_repository_check_config(
            mock_request, 999, sample_config_update, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/update_error.html",
            {"error_message": "Config not found"},
            status_code=404,
        )

    @pytest.mark.asyncio
    async def test_enable_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config enable returns correct HTMX response."""
        from borgitory.api.repository_check_configs import (
            enable_repository_check_config,
        )

        mock_service.enable_config.return_value = (
            True,
            "Config enabled successfully!",
            None,
        )

        result = await enable_repository_check_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.enable_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/action_success.html",
            {"message": "Config enabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_disable_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config disable returns correct HTMX response."""
        from borgitory.api.repository_check_configs import (
            disable_repository_check_config,
        )

        mock_service.disable_config.return_value = (
            True,
            "Config disabled successfully!",
            None,
        )

        result = await disable_repository_check_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.disable_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/action_success.html",
            {"message": "Config disabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_delete_config_success_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test successful config deletion returns correct HTMX response."""
        from borgitory.api.repository_check_configs import (
            delete_repository_check_config,
        )

        mock_service.delete_config.return_value = (True, "test-config", None)

        result = await delete_repository_check_config(
            mock_request, 1, mock_templates, mock_service
        )

        # Verify service was called
        mock_service.delete_config.assert_called_once_with(1)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/delete_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    @pytest.mark.asyncio
    async def test_delete_config_failure_htmx_response(
        self, mock_request, mock_templates, mock_service
    ) -> None:
        """Test failed config deletion returns correct HTMX error response."""
        from borgitory.api.repository_check_configs import (
            delete_repository_check_config,
        )

        mock_service.delete_config.return_value = (False, None, "Config not found")

        await delete_repository_check_config(
            mock_request, 999, mock_templates, mock_service
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/delete_error.html",
            {"error_message": "Config not found"},
            status_code=404,
        )

    def test_get_config_by_id_success(self, mock_service) -> None:
        """Test getting config by ID returns service result."""
        from borgitory.api.repository_check_configs import get_repository_check_config

        mock_config = MagicMock()
        mock_service.get_config_by_id.return_value = mock_config

        result = get_repository_check_config(1, mock_service)

        # Verify service was called
        mock_service.get_config_by_id.assert_called_once_with(1)

        # Verify result is returned
        assert result == mock_config

    def test_get_config_by_id_not_found(self, mock_service) -> None:
        """Test getting non-existent config by ID raises HTTPException."""
        from borgitory.api.repository_check_configs import get_repository_check_config
        from fastapi import HTTPException

        mock_service.get_config_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_repository_check_config(999, mock_service)

        assert exc_info.value.status_code == 404
        assert "Check policy not found" in str(exc_info.value.detail)

    def test_toggle_custom_options_show_custom(
        self, mock_request, mock_templates
    ) -> None:
        """Test toggling custom options shows custom options when no config selected."""
        from borgitory.api.repository_check_configs import toggle_custom_options

        toggle_custom_options(mock_request, mock_templates, check_config_id="")

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/custom_options.html",
            {"show_custom": True},
        )

    def test_toggle_custom_options_hide_custom(
        self, mock_request, mock_templates
    ) -> None:
        """Test toggling custom options hides custom options when config selected."""
        from borgitory.api.repository_check_configs import toggle_custom_options

        toggle_custom_options(mock_request, mock_templates, check_config_id="123")

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/custom_options.html",
            {"show_custom": False},
        )

    def test_update_check_options_repository_only_type(
        self, mock_request, mock_templates
    ) -> None:
        """Test update check options for repository_only check type."""
        from borgitory.api.repository_check_configs import update_check_options

        update_check_options(
            mock_request,
            mock_templates,
            check_type="repository_only",
            max_duration="3600",
            repair_mode="false",
        )

        # Verify correct template response with expected context
        mock_templates.TemplateResponse.assert_called_once()
        args, kwargs = mock_templates.TemplateResponse.call_args
        context = args[2]

        assert context["verify_data_disabled"] is True
        assert context["verify_data_opacity"] == "0.5"
        assert context["time_limit_display"] == "block"
        assert context["archive_filters_display"] == "none"

    def test_update_check_options_full_check_type(
        self, mock_request, mock_templates
    ) -> None:
        """Test update check options for full check type."""
        from borgitory.api.repository_check_configs import update_check_options

        update_check_options(
            mock_request,
            mock_templates,
            check_type="full",
            max_duration="",
            repair_mode="true",
        )

        # Verify correct template response with expected context
        mock_templates.TemplateResponse.assert_called_once()
        args, kwargs = mock_templates.TemplateResponse.call_args
        context = args[2]

        assert context["verify_data_disabled"] is False
        assert context["verify_data_opacity"] == "1"
        assert context["time_limit_display"] == "none"
        assert context["archive_filters_display"] == "block"
        assert context["repair_mode_checked"] is True
        assert context["repair_mode_disabled"] is False
