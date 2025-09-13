"""
Notification configuration API endpoints (HTML-only for HTMX).

Following HTMX principles: all endpoints return HTML fragments, never JSON.
"""

import logging
from typing import List
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.repository import NotificationConfig
from app.models.schemas import NotificationConfigCreate, NotificationConfigResponse
from app.models.enums import NotificationProvider
from app.dependencies import DatabaseDep, NotificationServiceDep, TemplatesDep
from app.services.interfaces import RepositoryValidationError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def list_notification_configs(
    request: Request,
    templates: TemplatesDep,
    db: DatabaseDep
):
    """
    List notification configurations as HTML for HTMX.
    
    HTMX PRINCIPLE: Returns HTML template, never JSON.
    """
    try:
        stmt = select(NotificationConfig).order_by(NotificationConfig.created_at.desc())
        configs = list(db.scalars(stmt))
        
        return templates.TemplateResponse(
            request,
            "partials/notifications/config_list.html",
            {"configs": configs}
        )
    except Exception as e:
        logger.error(f"Error loading notification configs: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Failed to load notification configurations"}
        )


@router.get("/form", response_class=HTMLResponse)
def get_notification_form(request: Request, templates: TemplatesDep):
    """
    Get notification configuration form.
    
    HTMX PRINCIPLE: Returns HTML form, never JSON.
    """
    return templates.TemplateResponse(
        request,
        "partials/notifications/config_form.html",
        {"providers": list(NotificationProvider)}
    )


@router.post("/create", response_class=HTMLResponse)
def create_notification_config(
    request: Request,
    templates: TemplatesDep,
    db: DatabaseDep,
    name: str = Form(...),
    provider: str = Form(NotificationProvider.PUSHOVER.value),
    user_key: str = Form(...),
    app_token: str = Form(...),
    enabled: bool = Form(True)
):
    """
    Create notification configuration returning HTML fragment.
    
    HTMX PRINCIPLE: Returns HTML success/error fragment, never JSON.
    """
    try:
        # Validate provider enum
        try:
            provider_enum = NotificationProvider(provider)
        except ValueError:
            return templates.TemplateResponse(
                request,
                "partials/notifications/config_error.html",
                {"error_message": f"Invalid provider: {provider}"}
            )
        
        # Check for duplicate name
        existing = db.scalar(select(NotificationConfig).where(NotificationConfig.name == name))
        if existing:
            return templates.TemplateResponse(
                request,
                "partials/notifications/config_error.html",
                {"error_message": f"Configuration '{name}' already exists"}
            )
        
        # Create configuration
        config = NotificationConfig(
            name=name,
            provider=provider_enum,
            enabled=enabled
        )
        config.set_pushover_credentials(user_key, app_token)
        
        db.add(config)
        db.commit()
        db.refresh(config)
        
        logger.info(f"Created notification config: {name}")
        
        return templates.TemplateResponse(
            request,
            "partials/notifications/config_success.html",
            {
                "config": config,
                "message": f"Notification configuration '{name}' created successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating notification config: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/config_error.html",
            {"error_message": str(e)}
        )


@router.post("/test/{config_id}", response_class=HTMLResponse)
async def test_notification_config(
    request: Request,
    templates: TemplatesDep,
    config_id: int,
    notification_service: NotificationServiceDep,
    db: DatabaseDep
):
    """
    Test notification configuration returning HTML fragment.
    
    HTMX PRINCIPLE: Returns HTML test result, never JSON.
    """
    config = db.get(NotificationConfig, config_id)
    if not config:
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Notification configuration not found"}
        )
    
    try:
        success = await notification_service.test_notification_config(config)
        
        if success:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_success.html",
                {"config_name": config.name}
            )
        else:
            return templates.TemplateResponse(
                request,
                "partials/notifications/test_error.html",
                {"config_name": config.name, "error_message": "Test notification failed"}
            )
            
    except Exception as e:
        logger.error(f"Error testing notification config {config_id}: {e}")
        return templates.TemplateResponse(
            request,
            "partials/notifications/test_error.html",
            {"config_name": config.name, "error_message": str(e)}
        )