"""
Tests for repository_check_configs API endpoints - HTMX and response validation focused
"""

import pytest
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.api.repository_check_configs import (
    create_repository_check_config,
    delete_repository_check_config,
    disable_repository_check_config,
    enable_repository_check_config,
    get_policy_form,
    get_repository_check_config,
    get_repository_check_config_edit_form,
    get_repository_check_configs_html,
    get_repository_check_form,
    toggle_custom_options,
    update_check_options,
    update_repository_check_config,
)
from borgitory.models.schemas import (
    CheckType,
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
)
from borgitory.services.repositories.repository_check_config_service import (
    RepositoryCheckConfigService,
)
from borgitory.dependencies import TemplatesDep


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database"""
    db = MagicMock(spec=AsyncSession)
    return db


@pytest.fixture
def mock_request() -> MagicMock:
    """Mock FastAPI request"""
    request = MagicMock(spec=Request)
    request.headers = {}
    return request


@pytest.fixture
def mock_templates() -> MagicMock:
    """Mock templates dependency"""
    templates = MagicMock()
    mock_response = MagicMock(spec=HTMLResponse)
    mock_response.headers = {}
    templates.TemplateResponse.return_value = mock_response
    return templates


@pytest.fixture
def mock_service() -> RepositoryCheckConfigService:
    """Mock RepositoryCheckConfigService"""
    service = AsyncMock(spec=RepositoryCheckConfigService)
    return cast(RepositoryCheckConfigService, service)


@pytest.fixture
def sample_config_create() -> RepositoryCheckConfigCreate:
    """Sample config creation data"""
    return RepositoryCheckConfigCreate(
        name="test-config",
        description="Test configuration",
        check_type=CheckType.REPOSITORY_ONLY,
        verify_data=False,
        repair_mode=False,
        save_space=False,
        max_duration=3600,
        archive_prefix=None,
        archive_glob=None,
        first_n_archives=None,
        last_n_archives=None,
    )


@pytest.fixture
def sample_config_update() -> RepositoryCheckConfigUpdate:
    """Sample config update data"""
    return RepositoryCheckConfigUpdate(
        name="updated-config",
        description="Updated configuration",
        check_type=CheckType.REPOSITORY_ONLY,
        verify_data=False,
        repair_mode=False,
        save_space=True,
        max_duration=3600,
        archive_prefix=None,
        archive_glob=None,
        first_n_archives=None,
        last_n_archives=None,
    )


class TestRepositoryCheckConfigsAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    async def test_create_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        sample_config_create: RepositoryCheckConfigCreate,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config creation returns correct HTMX response."""

        # Mock successful service response
        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.create_config.return_value = (True, mock_config, None)  # type: ignore[attr-defined]

        result = await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called with correct parameters
        mock_service.create_config.assert_called_once_with(  # type: ignore[attr-defined]
            db=mock_db,
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
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/create_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    async def test_create_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        sample_config_create: RepositoryCheckConfigCreate,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config creation returns correct HTMX error response."""

        # Mock service failure
        mock_service.create_config.return_value = (
            False,
            None,
            "Config name already exists",
        )

        await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/create_error.html",
            {"error_message": "Config name already exists"},
            status_code=400,
        )

    async def test_create_config_server_error_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: MagicMock,
        sample_config_create: RepositoryCheckConfigCreate,
        mock_db: AsyncSession,
    ) -> None:
        """Test server error during creation returns correct status code."""

        # Mock service failure with "Failed to" error
        mock_service.create_config.return_value = (
            False,
            None,
            "Failed to create config",
        )

        await create_repository_check_config(
            mock_request, sample_config_create, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response with 500 status
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/create_error.html",
            {"error_message": "Failed to create config"},
            status_code=500,
        )

    async def test_get_configs_html_success(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting configs HTML returns correct template response."""

        mock_configs = [MagicMock(), MagicMock()]
        mock_service.get_all_configs.return_value = mock_configs  # type: ignore[attr-defined]

        await get_repository_check_configs_html(
            mock_request, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.get_all_configs.assert_called_once_with(mock_db)  # type: ignore[attr-defined]

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/config_list_content.html",
            {"configs": mock_configs},
        )

    async def test_get_configs_html_exception(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting configs HTML with exception returns error template."""

        mock_service.get_all_configs.side_effect = Exception("Service error")

        await get_repository_check_configs_html(
            mock_request, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/common/error_message.html",
            {"error_message": "Error loading check policies: Service error"},
        )

    async def test_get_form_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting form returns correct HTMX template response."""

        mock_form_data = {"repositories": [MagicMock()], "check_configs": [MagicMock()]}
        mock_service.get_form_data.return_value = mock_form_data

        await get_repository_check_form(
            mock_request, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.get_form_data.assert_called_once()

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/form.html",
            mock_form_data,
        )

    async def test_get_policy_form_htmx_response(
        self, mock_request: MagicMock, mock_templates: TemplatesDep
    ) -> None:
        """Test getting policy form returns correct HTMX template response."""

        await get_policy_form(mock_request, mock_templates)

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/create_form.html",
            {},
        )

    async def test_get_config_edit_form_success(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting edit form returns correct HTMX template response."""

        mock_config = MagicMock()
        mock_service.get_config_by_id.return_value = mock_config  # type: ignore[attr-defined]

        await get_repository_check_config_edit_form(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.get_config_by_id.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/edit_form.html",
            {"config": mock_config, "is_edit_mode": True},
        )

    async def test_get_config_edit_form_not_found(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting edit form for non-existent config raises HTTPException."""

        mock_service.get_config_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_repository_check_config_edit_form(
                mock_request, 999, mock_templates, mock_service, db=mock_db
            )

        assert exc_info.value.status_code == 404
        assert "Check policy not found" in str(exc_info.value.detail)

    async def test_update_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        sample_config_update: RepositoryCheckConfigUpdate,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config update returns correct HTMX response."""

        mock_config = MagicMock()
        mock_config.name = "updated-config"
        mock_service.update_config.return_value = (True, mock_config, None)  # type: ignore[attr-defined]

        result = await update_repository_check_config(
            mock_request,
            1,
            sample_config_update,
            mock_templates,
            mock_service,
            db=mock_db,
        )

        # Verify service was called with correct parameters
        update_dict = sample_config_update.model_dump(exclude_unset=True)
        mock_service.update_config.assert_called_once_with(mock_db, 1, update_dict)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/update_success.html",
            {"config_name": "updated-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    async def test_update_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        sample_config_update: RepositoryCheckConfigUpdate,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config update returns correct HTMX error response."""

        mock_service.update_config.return_value = (False, None, "Config not found")

        await update_repository_check_config(
            mock_request,
            999,
            sample_config_update,
            mock_templates,
            mock_service,
            db=mock_db,
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/update_error.html",
            {"error_message": "Config not found"},
            status_code=404,
        )

    async def test_enable_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config enable returns correct HTMX response."""

        mock_service.enable_config.return_value = (  # type: ignore[attr-defined]
            True,
            "Config enabled successfully!",
            None,
        )

        result = await enable_repository_check_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.enable_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/action_success.html",
            {"message": "Config enabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    async def test_disable_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config disable returns correct HTMX response."""

        mock_service.disable_config.return_value = (  # type: ignore[attr-defined]
            True,
            "Config disabled successfully!",
            None,
        )

        result = await disable_repository_check_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.disable_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/action_success.html",
            {"message": "Config disabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    async def test_delete_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: RepositoryCheckConfigService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config deletion returns correct HTMX response."""

        mock_service.delete_config.return_value = (True, "test-config", None)  # type: ignore[attr-defined]

        result = await delete_repository_check_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.delete_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/repository_check/delete_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "checkConfigUpdate"

    async def test_delete_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: MagicMock,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config deletion returns correct HTMX error response."""

        mock_service.delete_config.return_value = (False, None, "Config not found")

        await delete_repository_check_config(
            mock_request, 999, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/delete_error.html",
            {"error_message": "Config not found"},
            status_code=404,
        )

    async def test_get_config_by_id_success(
        self, mock_service: RepositoryCheckConfigService, mock_db: AsyncSession
    ) -> None:
        """Test getting config by ID returns service result."""

        mock_config = MagicMock()
        mock_service.get_config_by_id.return_value = mock_config  # type: ignore[attr-defined]

        result = await get_repository_check_config(1, mock_service, mock_db)

        # Verify service was called
        mock_service.get_config_by_id.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify result is returned
        assert result == mock_config

    async def test_get_config_by_id_not_found(
        self, mock_service: RepositoryCheckConfigService, mock_db: AsyncSession
    ) -> None:
        """Test getting non-existent config by ID raises HTTPException."""

        mock_service.get_config_by_id.return_value = None  # type: ignore[attr-defined]

        with pytest.raises(HTTPException) as exc_info:
            await get_repository_check_config(999, mock_service, mock_db)

        assert exc_info.value.status_code == 404
        assert "Check policy not found" in str(exc_info.value.detail)

    async def test_toggle_custom_options_show_custom(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test toggling custom options shows custom options when no config selected."""

        await toggle_custom_options(mock_request, mock_templates, check_config_id="")

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/custom_options.html",
            {"show_custom": True},
        )

    async def test_toggle_custom_options_hide_custom(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test toggling custom options hides custom options when config selected."""

        await toggle_custom_options(mock_request, mock_templates, check_config_id="123")

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/custom_options.html",
            {"show_custom": False},
        )

    async def test_update_check_options_repository_only_type(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test update check options for repository_only check type."""

        await update_check_options(
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

    async def test_update_check_options_full_check_type(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test update check options for full check type."""

        await update_check_options(
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
