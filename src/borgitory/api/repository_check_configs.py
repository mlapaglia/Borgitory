from typing import List
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from borgitory.models.schemas import (
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
)
from borgitory.models.database import RepositoryCheckConfig

from borgitory.dependencies import TemplatesDep, RepositoryCheckConfigServiceDep

router = APIRouter()


@router.post("/", response_class=HTMLResponse)
async def create_repository_check_config(
    request: Request,
    config: RepositoryCheckConfigCreate,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Create a new repository check configuration"""
    success, created_config, error_msg = service.create_config(
        name=config.name,
        description=config.description,
        check_type=config.check_type,
        verify_data=config.verify_data,
        repair_mode=config.repair_mode,
        save_space=config.save_space,
        max_duration=config.max_duration,
        archive_prefix=config.archive_prefix,
        archive_glob=config.archive_glob,
        first_n_archives=config.first_n_archives,
        last_n_archives=config.last_n_archives,
    )

    if not success or not created_config:
        return templates.TemplateResponse(
            request,
            "partials/repository_check/create_error.html",
            {"error_message": error_msg},
            status_code=500 if error_msg and "Failed to" in error_msg else 400,
        )

    response = templates.TemplateResponse(
        request,
        "partials/repository_check/create_success.html",
        {"config_name": created_config.name},
    )
    response.headers["HX-Trigger"] = "checkConfigUpdate"
    return response


@router.get("/", response_class=HTMLResponse, response_model=None)
def get_repository_check_configs(
    service: RepositoryCheckConfigServiceDep,
) -> List[RepositoryCheckConfig]:
    """Get all repository check configurations"""
    return service.get_all_configs()


@router.get("/form", response_class=HTMLResponse)
async def get_repository_check_form(
    request: Request,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Get repository check form with all dropdowns populated"""
    form_data = service.get_form_data()

    return templates.TemplateResponse(
        request,
        "partials/repository_check/form.html",
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
        "partials/repository_check/create_form.html",
        {},
    )


@router.get("/html", response_class=HTMLResponse)
def get_repository_check_configs_html(
    request: Request,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Get repository check configurations as HTML"""
    try:
        configs = service.get_all_configs()
        return templates.TemplateResponse(
            request,
            "partials/repository_check/config_list_content.html",
            {"configs": configs},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {
                "error_message": f"Error loading check policies: {str(e)}",
            },
        )


@router.get("/toggle-custom-options", response_class=HTMLResponse)
def toggle_custom_options(
    request: Request,
    templates: TemplatesDep,
    check_config_id: str = "",
) -> HTMLResponse:
    """Toggle custom check options visibility based on policy selection"""

    show_custom = check_config_id == ""

    return templates.TemplateResponse(
        request,
        "partials/repository_check/custom_options.html",
        {
            "show_custom": show_custom,
        },
    )


@router.get("/update-options", response_class=HTMLResponse)
def update_check_options(
    request: Request,
    templates: TemplatesDep,
    check_type: str = "full",
    max_duration: str = "",
    repair_mode: str = "",
) -> HTMLResponse:
    """Update check options based on check type selection"""

    if check_type == "repository_only":
        verify_data_disabled = True
        verify_data_opacity = "0.5"
        time_limit_display = "block"
        archive_filters_display = "none"
    else:
        verify_data_disabled = False
        verify_data_opacity = "1"
        time_limit_display = "none"
        archive_filters_display = "block"

    repair_mode_checked = repair_mode and repair_mode.lower() in ["true", "on", "1"]
    repair_mode_disabled = bool(max_duration and max_duration.strip())
    if repair_mode_disabled and repair_mode_checked:
        repair_mode_checked = False

    return templates.TemplateResponse(
        request,
        "partials/repository_check/dynamic_options.html",
        {
            "verify_data_disabled": verify_data_disabled,
            "verify_data_opacity": verify_data_opacity,
            "time_limit_display": time_limit_display,
            "archive_filters_display": archive_filters_display,
            "repair_mode_checked": repair_mode_checked,
            "repair_mode_disabled": repair_mode_disabled,
            "max_duration": max_duration,
        },
    )


@router.get("/{config_id}", response_class=HTMLResponse, response_model=None)
def get_repository_check_config(
    config_id: int, service: RepositoryCheckConfigServiceDep
) -> RepositoryCheckConfig:
    """Get a specific repository check configuration"""
    config = service.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    return config


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_repository_check_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Get edit form for a specific repository check configuration"""
    try:
        config = service.get_config_by_id(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Check policy not found")

        context = {
            "config": config,
            "is_edit_mode": True,
        }

        return templates.TemplateResponse(
            request, "partials/repository_check/edit_form.html", context
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Check policy not found: {str(e)}")


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_repository_check_config(
    request: Request,
    config_id: int,
    update_data: RepositoryCheckConfigUpdate,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Update a repository check configuration"""
    update_dict = update_data.model_dump(exclude_unset=True)
    success, updated_config, error_msg = service.update_config(config_id, update_dict)

    if not success or not updated_config:
        return templates.TemplateResponse(
            request,
            "partials/repository_check/update_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 400,
        )

    response = templates.TemplateResponse(
        request,
        "partials/repository_check/update_success.html",
        {"config_name": updated_config.name},
    )
    response.headers["HX-Trigger"] = "checkConfigUpdate"
    return response


@router.patch("/{config_id}", response_class=HTMLResponse, response_model=None)
def patch_repository_check_config(
    config_id: int,
    update_data: RepositoryCheckConfigUpdate,
    service: RepositoryCheckConfigServiceDep,
) -> RepositoryCheckConfig:
    """Update a repository check configuration (PATCH method for backwards compatibility)"""
    update_dict = update_data.model_dump(exclude_unset=True)
    success, updated_config, error_msg = service.update_config(config_id, update_dict)

    if not success:
        if error_msg and "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)

    if updated_config is None:
        raise HTTPException(
            status_code=500, detail="Update succeeded but config is None"
        )

    return updated_config


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_repository_check_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Enable a repository check configuration"""
    success, success_msg, error_msg = service.enable_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/repository_check/action_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/repository_check/action_success.html",
        {"message": success_msg},
    )
    response.headers["HX-Trigger"] = "checkConfigUpdate"
    return response


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_repository_check_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Disable a repository check configuration"""
    success, success_msg, error_msg = service.disable_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/repository_check/action_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/repository_check/action_success.html",
        {"message": success_msg},
    )
    response.headers["HX-Trigger"] = "checkConfigUpdate"
    return response


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_repository_check_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: RepositoryCheckConfigServiceDep,
) -> HTMLResponse:
    """Delete a repository check configuration"""
    success, config_name, error_msg = service.delete_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/repository_check/delete_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/repository_check/delete_success.html",
        {"config_name": config_name},
    )
    response.headers["HX-Trigger"] = "checkConfigUpdate"
    return response
