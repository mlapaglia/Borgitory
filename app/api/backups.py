import logging
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import Repository, get_db

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/form")
async def get_backup_form(request: Request, db: Session = Depends(get_db)):
    """Get backup form with all dropdowns populated"""
    from app.models.database import CleanupConfig, CloudSyncConfig, NotificationConfig, RepositoryCheckConfig
    
    repositories = db.query(Repository).all()
    cleanup_configs = db.query(CleanupConfig).filter(CleanupConfig.enabled == True).all()
    cloud_sync_configs = db.query(CloudSyncConfig).filter(CloudSyncConfig.enabled == True).all()
    notification_configs = db.query(NotificationConfig).filter(NotificationConfig.enabled == True).all()
    check_configs = db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.enabled == True).all()
    
    return templates.TemplateResponse(
        "partials/backups/manual_form.html",
        {
            "request": request, 
            "repositories": repositories,
            "cleanup_configs": cleanup_configs,
            "cloud_sync_configs": cloud_sync_configs,
            "notification_configs": notification_configs,
            "check_configs": check_configs
        }
    )


