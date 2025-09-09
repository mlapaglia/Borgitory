"""
API endpoints for managing notification configurations (Pushover, etc.)
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import NotificationConfig, get_db
from app.models.schemas import (
    NotificationConfig as NotificationConfigSchema,
    NotificationConfigCreate,
)
from app.dependencies import PushoverServiceDep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


@router.post(
    "/", response_model=NotificationConfigSchema, status_code=status.HTTP_201_CREATED
)
async def create_notification_config(
    request: Request,
    notification_config: NotificationConfigCreate,
    db: Session = Depends(get_db),
):
    """Create a new notification configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        db_notification_config = NotificationConfig(
            name=notification_config.name,
            provider=notification_config.provider,
            notify_on_success=notification_config.notify_on_success,
            notify_on_failure=notification_config.notify_on_failure,
            enabled=True,
        )

        # Encrypt and store credentials
        db_notification_config.set_pushover_credentials(
            notification_config.user_key, notification_config.app_token
        )

        db.add(db_notification_config)
        db.commit()
        db.refresh(db_notification_config)

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/notifications/create_success.html",
                {"config_name": notification_config.name},
            )
            response.headers["HX-Trigger"] = "notificationUpdate"
            return response
        else:
            return db_notification_config

    except Exception as e:
        error_msg = f"Failed to create notification configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/notifications/create_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[NotificationConfigSchema])
def list_notification_configs(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """List all notification configurations"""
    notification_configs = db.query(NotificationConfig).offset(skip).limit(limit).all()
    return notification_configs


@router.get("/html", response_class=HTMLResponse)
def get_notification_configs_html(request: Request, db: Session = Depends(get_db)):
    """Get notification configurations as formatted HTML"""
    try:
        notification_configs_raw = db.query(NotificationConfig).all()

        # Process configs to add computed fields for template
        processed_configs = []
        for config in notification_configs_raw:
            # Build notification description
            notify_types = []
            if config.notify_on_success:
                notify_types.append("✅ Success")
            if config.notify_on_failure:
                notify_types.append("❌ Failures")

            notification_desc = (
                ", ".join(notify_types) if notify_types else "No notifications"
            )

            # Create processed config object for template
            processed_config = config.__dict__.copy()
            processed_config["notification_desc"] = notification_desc
            processed_configs.append(type("Config", (), processed_config)())

        return templates.get_template(
            "partials/notifications/config_list_content.html"
        ).render(request=request, configs=processed_configs)

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading notification configurations: {str(e)}", padding="4"
        )


@router.post("/{config_id}/test")
async def test_notification_config(
    request: Request,
    config_id: int,
    pushover_svc: PushoverServiceDep,
    db: Session = Depends(get_db),
):
    """Test a notification configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        notification_config = (
            db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        if not notification_config:
            error_msg = "Notification configuration not found"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/test_error.html",
                    {"error_message": error_msg},
                    status_code=404,
                )
            raise HTTPException(status_code=404, detail=error_msg)

        if notification_config.provider == "pushover":
            user_key, app_token = notification_config.get_pushover_credentials()
            result = await pushover_svc.test_pushover_connection(user_key, app_token)

            if is_htmx_request:
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
                return result
        else:
            error_msg = "Unsupported notification provider"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/test_error.html",
                    {"error_message": error_msg},
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail=error_msg)

    except Exception as e:
        error_msg = f"Test failed: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/{config_id}/enable")
async def enable_notification_config(
    request: Request, config_id: int, db: Session = Depends(get_db)
):
    """Enable a notification configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        notification_config = (
            db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        if not notification_config:
            error_msg = "Notification configuration not found"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/action_error.html",
                    {"error_message": error_msg},
                    status_code=404,
                )
            raise HTTPException(status_code=404, detail=error_msg)

        notification_config.enabled = True
        db.commit()

        message = f"Notification '{notification_config.name}' enabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/notifications/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "notificationUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_msg = f"Failed to enable notification: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/notifications/action_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/{config_id}/disable")
async def disable_notification_config(
    request: Request, config_id: int, db: Session = Depends(get_db)
):
    """Disable a notification configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        notification_config = (
            db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        if not notification_config:
            error_msg = "Notification configuration not found"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/action_error.html",
                    {"error_message": error_msg},
                    status_code=404,
                )
            raise HTTPException(status_code=404, detail=error_msg)

        notification_config.enabled = False
        db.commit()

        message = f"Notification '{notification_config.name}' disabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/notifications/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "notificationUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_msg = f"Failed to disable notification: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/notifications/action_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.delete("/{config_id}")
async def delete_notification_config(
    request: Request, config_id: int, db: Session = Depends(get_db)
):
    """Delete a notification configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        notification_config = (
            db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        if not notification_config:
            error_msg = "Notification configuration not found"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/notifications/action_error.html",
                    {"error_message": error_msg},
                    status_code=404,
                )
            raise HTTPException(status_code=404, detail=error_msg)

        config_name = notification_config.name
        db.delete(notification_config)
        db.commit()

        message = f"Notification configuration '{config_name}' deleted successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/notifications/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "notificationUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_msg = f"Failed to delete notification: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/notifications/action_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)
