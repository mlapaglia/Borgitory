"""
Tab Content API - Serves HTML fragments for lazy loading tabs via HTMX
"""
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.get("/repositories", response_class=HTMLResponse)
async def get_repositories_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve repositories tab content"""
    return templates.TemplateResponse(
        request, "partials/repositories/tab.html", {"current_user": current_user}
    )


@router.get("/backups", response_class=HTMLResponse)
async def get_backups_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve backups tab content"""
    return templates.TemplateResponse(
        request, "partials/backups/tab.html", {"current_user": current_user}
    )


@router.get("/schedules", response_class=HTMLResponse)
async def get_schedules_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve schedules tab content"""
    return templates.TemplateResponse(
        request, "partials/schedules/tab.html", {"current_user": current_user}
    )


@router.get("/cloud-sync", response_class=HTMLResponse)
async def get_cloud_sync_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve cloud sync tab content"""
    return templates.TemplateResponse(
        request, "partials/cloud_sync/tab.html", {"current_user": current_user}
    )


@router.get("/archives", response_class=HTMLResponse)
async def get_archives_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve archives tab content"""
    return templates.TemplateResponse(
        request, "partials/archives/tab.html", {"current_user": current_user}
    )


@router.get("/statistics", response_class=HTMLResponse)
async def get_statistics_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve statistics tab content"""
    return templates.TemplateResponse(
        request, "partials/statistics/tab.html", {"current_user": current_user}
    )


@router.get("/jobs", response_class=HTMLResponse)
async def get_jobs_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve jobs tab content"""
    return templates.TemplateResponse(
        request, "partials/jobs/tab.html", {"current_user": current_user}
    )


@router.get("/notifications", response_class=HTMLResponse)
async def get_notifications_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve notifications tab content"""
    return templates.TemplateResponse(
        request, "partials/notifications/tab.html", {"current_user": current_user}
    )


@router.get("/cleanup", response_class=HTMLResponse)
async def get_cleanup_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve cleanup tab content"""
    return templates.TemplateResponse(
        request, "partials/cleanup/tab.html", {"current_user": current_user}
    )


@router.get("/repository-check", response_class=HTMLResponse)
async def get_repository_check_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve repository check tab content"""
    return templates.TemplateResponse(
        request, "partials/repository_check/tab.html", {"current_user": current_user}
    )


@router.get("/debug", response_class=HTMLResponse)
async def get_debug_tab(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Serve debug tab content"""
    return templates.TemplateResponse(
        request, "partials/debug/tab.html", {"current_user": current_user}
    )