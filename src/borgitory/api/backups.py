import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from borgitory.models.database import (
    Repository,
    PruneConfig,
    CloudSyncConfig,
    NotificationConfig,
    RepositoryCheckConfig,
    get_db,
)
from borgitory.dependencies import TemplatesDep

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/form", response_class=HTMLResponse)
async def get_backup_form(
    request: Request,
    templates: TemplatesDep,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get backup form with all dropdowns populated"""
    repositories = db.query(Repository).all()
    prune_configs = db.query(PruneConfig).filter(PruneConfig.enabled.is_(True)).all()
    cloud_sync_configs = (
        db.query(CloudSyncConfig).filter(CloudSyncConfig.enabled.is_(True)).all()
    )
    notification_configs = (
        db.query(NotificationConfig).filter(NotificationConfig.enabled.is_(True)).all()
    )
    check_configs = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.enabled.is_(True))
        .all()
    )

    return templates.TemplateResponse(
        request,
        "partials/backups/manual_form.html",
        {
            "repositories": repositories,
            "prune_configs": prune_configs,
            "cloud_sync_configs": cloud_sync_configs,
            "notification_configs": notification_configs,
            "check_configs": check_configs,
        },
    )
