"""
API endpoints for managing notification configurations (Pushover, etc.)
"""

import logging

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from models.schemas import NotificationConfigCreate

from dependencies import (
    TemplatesDep,
    PushoverServiceDep,
    NotificationConfigServiceDep,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_config(
    request: Request,
    templates: TemplatesDep,
    notification_config: NotificationConfigCreate,
    service: NotificationConfigServiceDep,
):
    """Create a new notification configuration"""
    success, created_config, error_msg = service.create_config(
        name=notification_config.name,
        provider=notification_config.provider,
        notify_on_success=notification_config.notify_on_success,
        notify_on_failure=notification_config.notify_on_failure,
        user_key=notification_config.user_key,
        app_token=notification_config.app_token,
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/notifications/create_error.html",
            {"error_message": error_msg},
            status_code=500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/notifications/create_success.html",
        {"config_name": created_config.name},
    )
    response.headers["HX-Trigger"] = "notificationUpdate"
    return response


@router.get("/", response_class=HTMLResponse)
def list_notification_configs(
    service: NotificationConfigServiceDep,
    skip: int = 0,
    limit: int = 100,
):
    """List all notification configurations"""
    return service.get_all_configs(skip=skip, limit=limit)


@router.get("/html", response_class=HTMLResponse)
def get_notification_configs_html(
    request: Request,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Get notification configurations as formatted HTML"""
    try:
        processed_configs_data = service.get_configs_with_descriptions()

        # Convert dict data to objects for template compatibility
        processed_configs = []
        for config_data in processed_configs_data:
            processed_configs.append(type("Config", (), config_data)())

        return templates.get_template(
            "partials/notifications/config_list_content.html"
        ).render(request=request, configs=processed_configs)

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading notification configurations: {str(e)}", padding="4"
        )


@router.post("/{config_id}/test", response_class=HTMLResponse)
async def test_notification_config(
    request: Request,
    config_id: int,
    pushover_svc: PushoverServiceDep,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Test a notification configuration"""
    try:
        success, user_key, app_token, error_msg = service.get_config_credentials(
            config_id
        )

        if not success:
            status_code = 404 if "not found" in error_msg else 400
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": error_msg},
                status_code=status_code,
            )

        if user_key and app_token:  # Pushover provider
            result = await pushover_svc.test_pushover_connection(user_key, app_token)

            if result.get("status") == "success":
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/test_success.html",
                    {
                        "message": result.get("message", "Test successful"),
                    },
                )
            else:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/test_error.html",
                    {
                        "error_message": result.get("message", "Test failed"),
                    },
                    status_code=400,
                )
        else:
            error_msg = "Unsupported notification provider"
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": error_msg},
                status_code=400,
            )

    except Exception as e:
        error_msg = f"Test failed: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
async def enable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Enable a notification configuration"""
    success, success_msg, error_msg = service.enable_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/notifications/action_success.html",
        {"message": success_msg},
    )
    response.headers["HX-Trigger"] = "notificationUpdate"
    return response


@router.post("/{config_id}/disable", response_class=HTMLResponse)
async def disable_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Disable a notification configuration"""
    success, success_msg, error_msg = service.disable_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/notifications/action_success.html",
        {"message": success_msg},
    )
    response.headers["HX-Trigger"] = "notificationUpdate"
    return response


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_notification_config_edit_form(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
) -> HTMLResponse:
    """Get edit form for a specific notification configuration"""
    try:
        config = service.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        # Get decrypted credentials for edit form
        success, user_key, app_token, error_msg = service.get_config_credentials(
            config_id
        )
        if not success:
            user_key, app_token = "", ""

        context = {
            "config": config,
            "user_key": user_key or "",
            "app_token": app_token or "",
            "is_edit_mode": True,
        }

        return templates.TemplateResponse(
            request, "partials/notifications/edit_form.html", context
        )
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Notification configuration not found: {str(e)}"
        )


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_notification_config(
    request: Request,
    config_id: int,
    notification_config: NotificationConfigCreate,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Update a notification configuration"""
    success, updated_config, error_msg = service.update_config(
        config_id=config_id,
        name=notification_config.name,
        provider=notification_config.provider,
        notify_on_success=notification_config.notify_on_success,
        notify_on_failure=notification_config.notify_on_failure,
        user_key=notification_config.user_key,
        app_token=notification_config.app_token,
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/notifications/update_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/notifications/update_success.html",
        {"config_name": updated_config.name},
    )
    response.headers["HX-Trigger"] = "notificationUpdate"
    return response


@router.get("/form", response_class=HTMLResponse)
async def get_notification_form(
    request: Request, templates: TemplatesDep
) -> HTMLResponse:
    """Get notification creation form"""
    return templates.TemplateResponse(
        request,
        "partials/notifications/add_form.html",
        {},
    )


@router.delete("/{config_id}", response_class=HTMLResponse)
async def delete_notification_config(
    request: Request,
    config_id: int,
    templates: TemplatesDep,
    service: NotificationConfigServiceDep,
):
    """Delete a notification configuration"""
    success, config_name, error_msg = service.delete_config(config_id)

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/notifications/action_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    message = f"Notification configuration '{config_name}' deleted successfully!"

    response = templates.TemplateResponse(
        request,
        "partials/notifications/action_success.html",
        {"message": message},
    )
    response.headers["HX-Trigger"] = "notificationUpdate"
    return response
