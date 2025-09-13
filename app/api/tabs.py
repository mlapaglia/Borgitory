"""
Tab Content API - Serves HTML fragments for lazy loading tabs via HTMX
"""
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


def _render_tab_with_nav(request: Request, template_name: str, active_tab: str, context: dict):
    """Helper to render tab content with OOB navigation update."""
    # Main content
    main_response = templates.TemplateResponse(request, template_name, context)

    # Navigation sidebar with updated active state
    nav_context = {"active_tab": active_tab}
    nav_response = templates.TemplateResponse(request, "partials/navigation.html", nav_context)

    # Combine responses with OOB update
    combined_content = f"""
{main_response.body.decode()}
<div hx-swap-oob="outerHTML:#sidebar">
{nav_response.body.decode()}
</div>
"""
    return HTMLResponse(content=combined_content)


@router.get("/repositories", response_class=HTMLResponse)
async def get_repositories_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/repositories/tab.html",
        "repositories",
        {"current_user": current_user}
    )


@router.get("/backups", response_class=HTMLResponse)
async def get_backups_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/backups/tab.html",
        "backups",
        {"current_user": current_user}
    )


@router.get("/schedules", response_class=HTMLResponse)
async def get_schedules_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/schedules/tab.html",
        "schedules",
        {"current_user": current_user}
    )


@router.get("/cloud-sync", response_class=HTMLResponse)
async def get_cloud_sync_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/cloud_sync/tab.html",
        "cloud-sync",
        {"current_user": current_user}
    )


@router.get("/archives", response_class=HTMLResponse)
async def get_archives_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/archives/tab.html",
        "archives",
        {"current_user": current_user}
    )


@router.get("/statistics", response_class=HTMLResponse)
async def get_statistics_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/statistics/tab.html",
        "statistics",
        {"current_user": current_user}
    )


@router.get("/jobs", response_class=HTMLResponse)
async def get_jobs_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/jobs/tab.html",
        "jobs",
        {"current_user": current_user}
    )


@router.get("/notifications", response_class=HTMLResponse)
async def get_notifications_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/notifications/tab.html",
        "notifications",
        {"current_user": current_user}
    )


@router.get("/cleanup", response_class=HTMLResponse)
async def get_cleanup_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/cleanup/tab.html",
        "cleanup",
        {"current_user": current_user}
    )


@router.get("/repository-check", response_class=HTMLResponse)
async def get_repository_check_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/repository_check/tab.html",
        "repository-check",
        {"current_user": current_user}
    )


@router.get("/debug", response_class=HTMLResponse)
async def get_debug_tab(
    request: Request,
    current_user=Depends(get_current_user)
):
    return _render_tab_with_nav(
        request,
        "partials/debug/tab.html",
        "debug",
        {"current_user": current_user}
    )