"""
API endpoints for managing notification configurations with provider support.
"""

import logging
import os
import re
import html
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from starlette.templating import _TemplateResponse

from borgitory.dependencies import (
    NotificationConfigServiceDep,
    NotificationProviderRegistryDep,
    TemplatesDep,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_provider_template(provider: str, mode: str = "create") -> Optional[str]:
    """Get the appropriate template path for a provider (now unified for create/edit)"""
    if not provider:
        return None

    # Validate provider name: only allow alphanumerics, underscores, hyphens
    if not re.fullmatch(r"^[\w-]+$", provider):
        return None

    # Use unified template (no more separate _edit templates)
    template_path = f"partials/notifications/providers/{provider}_fields.html"
    full_path = f"src/borgitory/templates/{template_path}"

    # Ensure fully resolved full_path remains inside the intended provider templates dir
    base_templates_dir = os.path.realpath(
        os.path.normpath("src/borgitory/templates/partials/notifications/providers/")
    )
    real_full_path = os.path.realpath(os.path.normpath(full_path))
    if not real_full_path.startswith(base_templates_dir + os.sep):
        return None

    if os.path.exists(real_full_path):
        return template_path

    return None


@router.get("/provider-fields")
async def get_provider_fields(
    request: Request,
    templates: TemplatesDep,
    registry: NotificationProviderRegistryDep,
    provider: Optional[str] = None,
    mode: str = "create",
) -> HTMLResponse:
    """Get provider-specific form fields"""
    if not provider:
        return HTMLResponse("")

    template_path = _get_provider_template(provider, mode)
    if not template_path:
        return HTMLResponse(
            f'<div class="text-red-500">No template found for provider: {html.escape(provider)}</div>'
        )

    try:
        submit_button_text = (
            "Add Notification" if mode == "create" else "Update Notification"
        )

        context = {
            "provider": provider,
            "mode": mode,
            "submit_button_text": submit_button_text,
        }

        # For edit mode, include any configuration values passed via query params or form data
        if mode == "edit":
            # Get configuration data from query parameters (for HTMX requests)
            for key, value in request.query_params.items():
                if key not in ["provider", "mode"]:
                    context[key] = value

        return HTMLResponse(
            templates.get_template(template_path).render(request=request, **context)
        )
    except Exception as e:
        logger.error(f"Error rendering provider template {template_path}: {e}")
        return HTMLResponse(
            '<div class="text-red-500">An error occurred while loading provider fields.</div>'
        )


@router.post("/", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_config(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Create a new notification configuration using the provider system"""
    try:
        # Get form data
        form_data = await request.form()

        # Extract basic fields
        name_field = form_data.get("name", "")
        provider_field = form_data.get("provider", "")

        # Handle both str and UploadFile types
        name = name_field.strip() if isinstance(name_field, str) else ""
        provider = provider_field.strip() if isinstance(provider_field, str) else ""

        if not name or not provider:
            return templates.TemplateResponse(
                request,
                "partials/notifications/create_error.html",
                {"error_message": "Name and provider are required"},
                status_code=400,
            )

        # Extract provider-specific configuration
        provider_config = {}
        for key, value in form_data.items():
            if key not in ["name", "provider"] and value:
                provider_config[key] = value

        # Create config using service
        try:
            db_config = config_service.create_config(
                name=name, provider=provider, provider_config=provider_config
            )
        except HTTPException as e:
            return templates.TemplateResponse(
                request,
                "partials/notifications/create_error.html",
                {"error_message": e.detail},
                status_code=e.status_code,
            )

        response = templates.TemplateResponse(
            request,
            "partials/notifications/create_success.html",
            {"config_name": db_config.name},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except Exception as e:
        logger.error(f"Error creating notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/create_error.html",
            {"error_message": f"Failed to create notification: {str(e)}"},
            status_code=500,
        )


@router.get("/html", response_class=HTMLResponse)
def get_notification_configs_html(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> HTMLResponse:
    """Get notification configurations as formatted HTML"""
    try:
        configs = config_service.get_all_configs()

        return HTMLResponse(
            templates.get_template(
                "partials/notifications/config_list_content.html"
            ).render(request=request, configs=configs)
        )

    except Exception as e:
        return HTMLResponse(
            templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading notification configurations: {str(e)}",
                padding="4",
            )
        )


@router.post("/{config_id}/test", response_class=HTMLResponse)
async def test_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Test a notification configuration using the provider system"""
    try:
        # Pass encryption service like cloud sync does
        from borgitory.dependencies import get_notification_service_singleton

        notification_service = get_notification_service_singleton()
        success, message = await config_service.test_config_with_service(
            config_id, notification_service
        )

        if success:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_success.html",
                {"message": message},
            )
        else:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": message},
                status_code=400,
            )

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        logger.error(f"Error testing notification config {config_id}: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": f"Test failed: {str(e)}"},
            status_code=500,
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Enable a notification configuration"""
    try:
        success, message = config_service.enable_config(config_id)

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to enable notification: {str(e)}"},
            status_code=500,
        )


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Disable a notification configuration"""
    try:
        success, message = config_service.disable_config(config_id)

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to disable notification: {str(e)}"},
            status_code=500,
        )


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_notification_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> HTMLResponse:
    """Get edit form for a specific notification configuration"""
    try:
        config, decrypted_config = config_service.get_config_with_decrypted_data(
            config_id
        )

        context = {
            "config": config,
            "decrypted_config": decrypted_config,
            "provider_template": _get_provider_template(config.provider, "edit"),
            "is_edit_mode": True,
            "mode": "edit",  # Pass mode for unified template
        }

        # Add decrypted config values to context for template rendering
        context.update(decrypted_config)

        return templates.TemplateResponse(
            request, "partials/notifications/edit_form.html", context
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error loading edit form: {str(e)}"
        )


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Update a notification configuration"""
    try:
        # Get form data
        form_data = await request.form()

        # Extract basic fields
        name_field = form_data.get("name", "")
        provider_field = form_data.get("provider", "")

        # Handle both str and UploadFile types
        name = name_field.strip() if isinstance(name_field, str) else ""
        provider = provider_field.strip() if isinstance(provider_field, str) else ""

        if not name or not provider:
            return templates.TemplateResponse(
                request,
                "partials/notifications/update_error.html",
                {"error_message": "Name and provider are required"},
                status_code=400,
            )

        # Extract provider-specific configuration
        provider_config = {}
        for key, value in form_data.items():
            if key not in ["name", "provider"] and value:
                provider_config[key] = value

        # Update config using service
        try:
            updated_config = config_service.update_config(
                config_id=config_id,
                name=name,
                provider=provider,
                provider_config=provider_config,
            )
        except HTTPException as e:
            return templates.TemplateResponse(
                request,
                "partials/notifications/update_error.html",
                {"error_message": e.detail},
                status_code=e.status_code,
            )

        response = templates.TemplateResponse(
            request,
            "partials/notifications/update_success.html",
            {"config_name": updated_config.name},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except Exception as e:
        logger.error(f"Error updating notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/update_error.html",
            {"error_message": f"Failed to update notification: {str(e)}"},
            status_code=500,
        )


@router.get("/form", response_class=HTMLResponse)
async def get_notification_form(
    request: Request,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> HTMLResponse:
    """Get notification creation form with provider support"""
    try:
        supported_providers = config_service.get_supported_providers()

        return templates.TemplateResponse(
            request,
            "partials/notifications/add_form.html",
            {"supported_providers": supported_providers},
        )
    except Exception as e:
        logger.error(f"Error getting notification form: {e}")
        return HTMLResponse(
            '<div class="text-red-500">Failed to load notification form.</div>',
            status_code=500,
        )


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    config_service: NotificationConfigServiceDep,
) -> _TemplateResponse:
    """Delete a notification configuration"""
    try:
        success, config_name = config_service.delete_config(config_id)

        message = f"Notification configuration '{config_name}' deleted successfully!"

        response = templates.TemplateResponse(
            request,
            "partials/notifications/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "notificationUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": e.detail},
            status_code=e.status_code,
        )
    except Exception as e:
        logger.error(f"Error deleting notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": f"Failed to delete notification: {str(e)}"},
            status_code=500,
        )
