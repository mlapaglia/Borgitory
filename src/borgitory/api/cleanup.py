"""
API endpoints for managing prune configurations (archive pruning policies)
"""

import logging
from typing import List
from borgitory.models.database import CleanupConfig

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import _TemplateResponse

from borgitory.models.schemas import (
    CleanupConfig as CleanupConfigSchema,
    CleanupConfigCreate,
    CleanupConfigUpdate,
)

from borgitory.dependencies import (
    TemplatesDep,
    CleanupServiceDep,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/form", response_class=HTMLResponse)
async def get_cleanup_form(
    request: Request,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Get manual cleanup form with repositories populated"""
    form_data = service.get_form_data()

    return templates.TemplateResponse(
        request,
        "partials/prune/config_form.html",
        form_data,
    )


@router.get("/policy-form", response_class=HTMLResponse)
async def get_policy_form(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Get policy creation form"""
    return templates.TemplateResponse(
        request,
        "partials/prune/create_form.html",
        {},
    )


@router.get("/strategy-fields", response_class=HTMLResponse)
async def get_strategy_fields(
    request: Request, templates: TemplatesDep, strategy: str = "simple"
) -> HTMLResponse:
    """Get dynamic strategy fields based on selection"""
    return templates.TemplateResponse(
        request,
        "partials/prune/strategy_fields.html",
        {"strategy": strategy},
    )


@router.post("/", response_class=HTMLResponse)
async def create_cleanup_config(
    request: Request,
    cleanup_config: CleanupConfigCreate,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Create a new cleanup configuration"""
    success, config, error_message = service.create_cleanup_config(cleanup_config)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/create_success.html",
            {"config_name": config.name},
        )
        response.headers["HX-Trigger"] = "cleanupConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/create_error.html",
            {"error_message": error_message},
            status_code=400,
        )


@router.get("/", response_model=List[CleanupConfigSchema])
def list_cleanup_configs(
    service: CleanupServiceDep,
    skip: int = 0,
    limit: int = 100,
) -> List[CleanupConfig]:
    """List all cleanup configurations"""
    return service.get_cleanup_configs(skip, limit)


@router.get("/html", response_class=HTMLResponse)
def get_cleanup_configs_html(
    request: Request,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> str:
    """Get cleanup configurations as formatted HTML"""
    try:
        processed_configs = service.get_configs_with_descriptions()

        return templates.get_template("partials/prune/config_list_content.html").render(
            request=request, configs=processed_configs
        )

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading cleanup configurations: {str(e)}", padding="4"
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_cleanup_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> _TemplateResponse:
    """Enable a cleanup configuration"""
    success, config, error_message = service.enable_cleanup_config(config_id)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Prune policy '{config.name}' enabled successfully!"},
        )
        response.headers["HX-Trigger"] = "cleanupConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_cleanup_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Disable a cleanup configuration"""
    success, config, error_message = service.disable_cleanup_config(config_id)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Prune policy '{config.name}' disabled successfully!"},
        )
        response.headers["HX-Trigger"] = "cleanupConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_cleanup_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Get edit form for a specific cleanup configuration"""
    config = service.get_cleanup_config_by_id(config_id)

    if not config:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Cleanup configuration not found")

    context = {
        "config": config,
        "is_edit_mode": True,
    }

    return templates.TemplateResponse(request, "partials/prune/edit_form.html", context)


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_cleanup_config(
    request: Request,
    config_id: int,
    config_update: CleanupConfigUpdate,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Update a cleanup configuration"""
    success, updated_config, error_message = service.update_cleanup_config(
        config_id, config_update
    )

    if success and updated_config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/update_success.html",
            {"config_name": updated_config.name},
        )
        response.headers["HX-Trigger"] = "cleanupConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/update_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_cleanup_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: CleanupServiceDep,
) -> HTMLResponse:
    """Delete a cleanup configuration"""
    success, config_name, error_message = service.delete_cleanup_config(config_id)

    if success:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Cleanup configuration '{config_name}' deleted successfully!"},
        )
        response.headers["HX-Trigger"] = "cleanupConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )
