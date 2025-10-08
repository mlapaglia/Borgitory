import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from borgitory.models.database import (
    Repository,
    PruneConfig,
    CloudSyncConfig,
    NotificationConfig,
    RepositoryCheckConfig,
)
from borgitory.dependencies import TemplatesDep, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/form", response_class=HTMLResponse)
async def get_backup_form(
    request: Request,
    templates: TemplatesDep,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get backup form with all dropdowns populated"""
    repositories_result = await db.execute(select(Repository))
    repositories = list(repositories_result.scalars().all())

    prune_configs_result = await db.execute(
        select(PruneConfig).where(PruneConfig.enabled.is_(True))
    )
    prune_configs = list(prune_configs_result.scalars().all())

    cloud_sync_configs_result = await db.execute(
        select(CloudSyncConfig).where(CloudSyncConfig.enabled.is_(True))
    )
    cloud_sync_configs = list(cloud_sync_configs_result.scalars().all())

    notification_configs_result = await db.execute(
        select(NotificationConfig).where(NotificationConfig.enabled.is_(True))
    )
    notification_configs = list(notification_configs_result.scalars().all())

    check_configs_result = await db.execute(
        select(RepositoryCheckConfig).where(RepositoryCheckConfig.enabled.is_(True))
    )
    check_configs = list(check_configs_result.scalars().all())

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
