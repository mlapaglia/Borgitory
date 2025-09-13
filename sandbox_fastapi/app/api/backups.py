"""
Backup form API endpoints for frontend integration.

Provides HTMX-compatible endpoints for backup form functionality.
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.dependencies import RepositoryManagementServiceDep, DatabaseDep, TemplatesDep
from app.models.repository import NotificationConfig
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/form", response_class=HTMLResponse)
async def get_backup_form(
    request: Request,
    templates: TemplatesDep,
    repository_service: RepositoryManagementServiceDep,
    db: DatabaseDep
):
    """
    Get backup form with populated repository dropdown.
    
    This endpoint demonstrates:
    - Clean FastAPI DI for form data population
    - Template integration with service layer
    - HTMX-compatible response patterns
    """
    try:
        # Get repositories for dropdown using service layer
        repositories = repository_service.list_repositories(db, 0, 1000)  # Get all for dropdown
        
        # Get notification configs for dropdown using proper DI
        stmt = select(NotificationConfig).where(NotificationConfig.enabled == True).order_by(NotificationConfig.name)
        notification_configs = list(db.scalars(stmt))
        
        return templates.TemplateResponse(
            request,
            "partials/backups/backup_form.html",
            {
                "repositories": repositories,
                "notification_configs": notification_configs
            }
        )
        
    except Exception as e:
        logger.error(f"Error loading backup form: {e}")
        return templates.TemplateResponse(
            request,
            "partials/common/error.html",
            {"error_message": "Failed to load backup form"}
        )