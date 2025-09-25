"""
API endpoints for managing prune configurations (archive pruning policies)
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.templating import _TemplateResponse

from borgitory.models.schemas import (
    PruneConfigCreate,
    PruneConfigUpdate,
)

from borgitory.dependencies import (
    TemplatesDep,
    PruneServiceDep,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/form", response_class=HTMLResponse)
async def get_prune_form(
    request: Request,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Get manual prune form with repositories populated"""
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
async def create_prune_config(
    request: Request,
    prune_config: PruneConfigCreate,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Create a new prune configuration"""
    success, config, error_message = service.create_prune_config(prune_config)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/create_success.html",
            {"config_name": config.name},
        )
        response.headers["HX-Trigger"] = "pruneConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/create_error.html",
            {"error_message": error_message},
            status_code=400,
        )


@router.get("/", response_class=HTMLResponse)
def get_prune_configs(
    request: Request,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> str:
    """Get prune configurations as formatted HTML"""
    try:
        processed_configs = service.get_configs_with_descriptions()

        return templates.get_template("partials/prune/config_list_content.html").render(
            request=request, configs=processed_configs
        )

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading prune configurations: {str(e)}", padding="4"
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_prune_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> _TemplateResponse:
    """Enable a prune configuration"""
    success, config, error_message = service.enable_prune_config(config_id)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Prune policy '{config.name}' enabled successfully!"},
        )
        response.headers["HX-Trigger"] = "pruneConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_prune_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Disable a prune configuration"""
    success, config, error_message = service.disable_prune_config(config_id)

    if success and config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Prune policy '{config.name}' disabled successfully!"},
        )
        response.headers["HX-Trigger"] = "pruneConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_prune_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Get edit form for a specific prune configuration"""
    config = service.get_prune_config_by_id(config_id)

    if not config:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Prune configuration not found")

    context = {
        "config": config,
        "is_edit_mode": True,
    }

    return templates.TemplateResponse(request, "partials/prune/edit_form.html", context)


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_prune_config(
    request: Request,
    config_id: int,
    config_update: PruneConfigUpdate,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Update a prune configuration"""
    success, updated_config, error_message = service.update_prune_config(
        config_id, config_update
    )

    if success and updated_config:
        response = templates.TemplateResponse(
            request,
            "partials/prune/update_success.html",
            {"config_name": updated_config.name},
        )
        response.headers["HX-Trigger"] = "pruneConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/update_error.html",
            {"error_message": error_message},
            status_code=404,
        )


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_prune_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: PruneServiceDep,
) -> HTMLResponse:
    """Delete a prune configuration"""
    success, config_name, error_message = service.delete_prune_config(config_id)

    if success:
        response = templates.TemplateResponse(
            request,
            "partials/prune/action_success.html",
            {"message": f"Prune configuration '{config_name}' deleted successfully!"},
        )
        response.headers["HX-Trigger"] = "pruneConfigUpdate"
        return response
    else:
        return templates.TemplateResponse(
            request,
            "partials/prune/action_error.html",
            {"error_message": error_message},
            status_code=404,
        )
