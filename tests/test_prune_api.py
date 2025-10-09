"""
Tests for prune API endpoints - HTMX and response validation focused
"""

from typing import Any, cast
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.api.prune import (
    create_prune_config,
    delete_prune_config,
    disable_prune_config,
    enable_prune_config,
    get_policy_form,
    get_prune_config_edit_form,
    get_prune_configs,
    get_prune_form,
    get_strategy_fields,
    update_prune_config,
)
from borgitory.dependencies import TemplatesDep
from borgitory.models.schemas import PruneStrategy, PruneConfigCreate, PruneConfigUpdate
from borgitory.services.prune_service import (
    PruneConfigDeleteResult,
    PruneConfigOperationResult,
    PruneService,
)


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
    templates = MagicMock(spec=TemplatesDep)
    mock_response = MagicMock(spec=HTMLResponse)
    mock_response.headers = {}
    templates.TemplateResponse.return_value = mock_response
    templates.get_template.return_value.render.return_value = "mocked html content"
    return templates


@pytest.fixture
def mock_service() -> PruneService:
    """Mock PruneService"""
    service = AsyncMock(spec=PruneService)
    return cast(PruneService, service)


@pytest.fixture
def sample_config_create() -> PruneConfigCreate:
    """Sample config creation data"""
    return PruneConfigCreate(
        name="test-config",
        strategy=PruneStrategy.SIMPLE,
        keep_within_days=30,
        keep_secondly=0,
        keep_minutely=0,
        keep_hourly=0,
        keep_daily=0,
        keep_weekly=0,
        keep_monthly=0,
        keep_yearly=0,
    )


@pytest.fixture
def sample_config_update() -> PruneConfigUpdate:
    """Sample config update data"""
    return PruneConfigUpdate(
        name="updated-config",
        keep_within_days=60,
        keep_secondly=0,
        keep_minutely=0,
        keep_hourly=0,
        keep_daily=0,
        keep_weekly=0,
        keep_monthly=0,
        keep_yearly=0,
    )


class TestPruneAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    async def test_get_prune_form_success(
        self,
        mock_request: MagicMock,
        mock_templates: MagicMock,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting prune form returns correct template response."""

        mock_form_data: dict[str, Any] = {"repositories": []}
        mock_service.get_form_data.return_value = mock_form_data  # type: ignore[attr-defined]

        await get_prune_form(mock_request, mock_templates, mock_service, db=mock_db)

        mock_service.get_form_data.assert_called_once()  # type: ignore[attr-defined]

        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/config_form.html",
            mock_form_data,
        )

    async def test_get_policy_form_success(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test getting policy form returns correct template response."""

        await get_policy_form(mock_request, mock_templates)

        # Verify template was rendered
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/create_form.html",
            {},
        )

    async def test_get_strategy_fields_success(
        self, mock_request: MagicMock, mock_templates: MagicMock
    ) -> None:
        """Test getting strategy fields returns correct template response."""

        await get_strategy_fields(mock_request, mock_templates, strategy="advanced")

        # Verify template was rendered
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/prune/strategy_fields.html",
            {"strategy": "advanced"},
        )

    async def test_create_prune_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        sample_config_create: PruneConfigCreate,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config creation returns correct HTMX response."""

        # Mock successful service response
        mock_config = MagicMock()
        mock_config.name = "test-config"

        mock_service.create_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=True, config=mock_config, error_message=None
        )

        result = await create_prune_config(
            mock_request, sample_config_create, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called with correct parameters
        mock_service.create_prune_config.assert_called_once_with(
            mock_db, sample_config_create
        )  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/create_success.html",
            {"config_name": "test-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "pruneConfigUpdate"

    async def test_create_prune_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        sample_config_create: PruneConfigCreate,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config creation returns correct HTMX error response."""

        mock_service.create_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=False,
            config=None,
            error_message="Failed to create prune configuration",
        )

        await create_prune_config(
            mock_request, sample_config_create, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/create_error.html",
            {"error_message": "Failed to create prune configuration"},
            status_code=400,
        )

    async def test_get_prune_configs_exception(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting configs HTML with exception returns error template."""

        mock_service.get_configs_with_descriptions.side_effect = Exception(  # type: ignore[attr-defined]
            "Service error"
        )

        await get_prune_configs(mock_request, mock_templates, mock_service, db=mock_db)

        # Verify error template response
        mock_templates.get_template.assert_called_with("partials/jobs/error_state.html")  # type: ignore[attr-defined]

    async def test_enable_prune_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config enable returns correct HTMX response."""

        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.enable_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=True, config=mock_config, error_message=None
        )

        result = await enable_prune_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.enable_prune_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Prune policy 'test-config' enabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "pruneConfigUpdate"

    async def test_enable_prune_config_not_found_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test enabling non-existent config returns correct HTMX error response."""

        mock_service.enable_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=False,
            config=None,
            error_message="Prune configuration not found",
        )

        await enable_prune_config(
            mock_request, 999, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Prune configuration not found"},
            status_code=404,
        )

    async def test_disable_prune_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config disable returns correct HTMX response."""
        mock_config = MagicMock()
        mock_config.name = "test-config"
        mock_service.disable_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=True, config=mock_config, error_message=None
        )

        result = await disable_prune_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.disable_prune_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Prune policy 'test-config' disabled successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "pruneConfigUpdate"

    async def test_disable_prune_config_not_found_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test disabling non-existent config returns correct HTMX error response."""
        mock_service.disable_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=False,
            config=None,
            error_message="Prune configuration not found",
        )

        await disable_prune_config(
            mock_request, 999, mock_templates, mock_service, db=mock_db
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Prune configuration not found"},
            status_code=404,
        )

    async def test_get_prune_config_edit_form_success(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting edit form returns correct template response."""

        mock_config = MagicMock()
        mock_service.get_prune_config_by_id.return_value = mock_config  # type: ignore[attr-defined]

        await get_prune_config_edit_form(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.get_prune_config_by_id.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify correct template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/edit_form.html",
            {
                "config": mock_config,
                "is_edit_mode": True,
            },
        )

    async def test_get_prune_config_edit_form_not_found(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test getting edit form for non-existent config raises HTTPException."""
        mock_service.get_prune_config_by_id.return_value = None  # type: ignore[attr-defined]

        with pytest.raises(HTTPException) as exc_info:
            await get_prune_config_edit_form(
                mock_request, 999, mock_templates, mock_service, db=mock_db
            )

        assert exc_info.value.status_code == 404
        assert "Prune configuration not found" in str(exc_info.value.detail)

    async def test_update_prune_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        sample_config_update: PruneConfigUpdate,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config update returns correct HTMX response."""

        mock_config = MagicMock()
        mock_config.name = "updated-config"
        mock_service.update_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=True, config=mock_config, error_message=None
        )

        result = await update_prune_config(
            mock_request,
            1,
            sample_config_update,
            mock_templates,
            mock_service,
            db=mock_db,
        )

        # Verify service was called with correct parameters
        mock_service.update_prune_config.assert_called_once_with(
            mock_db, 1, sample_config_update
        )  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/update_success.html",
            {"config_name": "updated-config"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "pruneConfigUpdate"

    async def test_update_prune_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        sample_config_update: PruneConfigUpdate,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config update returns correct HTMX error response."""

        mock_service.update_prune_config.return_value = PruneConfigOperationResult(  # type: ignore[attr-defined]
            success=False,
            config=None,
            error_message="Prune configuration not found",
        )

        await update_prune_config(
            mock_request,
            999,
            sample_config_update,
            mock_templates,
            mock_service,
            db=mock_db,
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/update_error.html",
            {"error_message": "Prune configuration not found"},
            status_code=404,
        )

    async def test_delete_prune_config_success_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test successful config deletion returns correct HTMX response."""
        mock_service.delete_prune_config.return_value = PruneConfigDeleteResult(  # type: ignore[attr-defined]
            success=True, config_name="test-config", error_message=None
        )

        result = await delete_prune_config(
            mock_request, 1, mock_templates, mock_service, db=mock_db
        )

        # Verify service was called
        mock_service.delete_prune_config.assert_called_once_with(mock_db, 1)  # type: ignore[attr-defined]

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_success.html",
            {"message": "Prune configuration 'test-config' deleted successfully!"},
        )

        # Verify HX-Trigger header is set
        assert result.headers["HX-Trigger"] == "pruneConfigUpdate"

    async def test_delete_prune_config_failure_htmx_response(
        self,
        mock_request: MagicMock,
        mock_templates: TemplatesDep,
        mock_service: PruneService,
        mock_db: AsyncSession,
    ) -> None:
        """Test failed config deletion returns correct HTMX error response."""
        mock_service.delete_prune_config.return_value = PruneConfigDeleteResult(  # type: ignore[attr-defined]
            success=False,
            config_name=None,
            error_message="Prune configuration not found",
        )

        await delete_prune_config(
            mock_request, 999, mock_templates, mock_service, db=mock_db
        )

        mock_templates.TemplateResponse.assert_called_once_with(  # type: ignore[attr-defined]
            mock_request,
            "partials/prune/action_error.html",
            {"error_message": "Prune configuration not found"},
            status_code=404,
        )
