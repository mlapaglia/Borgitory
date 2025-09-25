"""
Tab Content API - Serves HTML fragments for lazy loading tabs via HTMX
"""

import logging
from typing import Dict
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse

from borgitory.api.auth import get_current_user
from borgitory.dependencies import (
    ProviderRegistryDep,
    NotificationProviderRegistryDep,
    get_templates,
)
from borgitory.models.database import User

router = APIRouter()
logger = logging.getLogger(__name__)
templates = get_templates()


def _render_tab_with_nav(
    request: Request, template_name: str, active_tab: str, context: Dict[str, object]
) -> HTMLResponse:
    """Helper to render tab content with OOB navigation update."""
    # Main content
    main_response = templates.TemplateResponse(request, template_name, context)

    # Navigation sidebar with updated active state
    nav_context = {"active_tab": active_tab}
    nav_response = templates.TemplateResponse(
        request, "partials/navigation.html", nav_context
    )

    # Combine responses with OOB update
    combined_content = f"""
{bytes(main_response.body).decode()}
<div hx-swap-oob="outerHTML:#sidebar">
{bytes(nav_response.body).decode()}
</div>
"""
    return HTMLResponse(content=combined_content)


@router.get("/repositories", response_class=HTMLResponse)
async def get_repositories_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/repositories/tab.html",
        "repositories",
        {"current_user": current_user},
    )


@router.get("/backups", response_class=HTMLResponse)
async def get_backups_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request, "partials/backups/tab.html", "backups", {"current_user": current_user}
    )


@router.get("/schedules", response_class=HTMLResponse)
async def get_schedules_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/schedules/tab.html",
        "schedules",
        {"current_user": current_user},
    )


@router.get("/cloud-sync", response_class=HTMLResponse)
async def get_cloud_sync_tab(
    request: Request,
    registry: ProviderRegistryDep,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    # Generate supported providers list directly from registry
    provider_info = registry.get_all_provider_info()
    supported_providers = []
    for provider_name, info in provider_info.items():
        supported_providers.append(
            {
                "value": provider_name,
                "label": info.label,
                "description": info.description,
            }
        )
        supported_providers = sorted(supported_providers, key=lambda x: str(x["value"]))

    return _render_tab_with_nav(
        request,
        "partials/cloud_sync/tab.html",
        "cloud-sync",
        {
            "current_user": current_user,
            "supported_providers": supported_providers,
        },
    )


@router.get("/archives", response_class=HTMLResponse)
async def get_archives_tab(
    request: Request,
    current_user: User = Depends(get_current_user),
    preselect_repo: str = "",
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/archives/tab.html",
        "archives",
        {"current_user": current_user, "preselect_repo": preselect_repo},
    )


@router.get("/statistics", response_class=HTMLResponse)
async def get_statistics_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/statistics/tab.html",
        "statistics",
        {"current_user": current_user},
    )


@router.get("/jobs", response_class=HTMLResponse)
async def get_jobs_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request, "partials/jobs/tab.html", "jobs", {"current_user": current_user}
    )


@router.get("/notifications", response_class=HTMLResponse)
async def get_notifications_tab(
    request: Request,
    notification_registry: NotificationProviderRegistryDep,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    # Generate supported providers list directly from registry
    provider_info = notification_registry.get_all_provider_info()
    logger.info(f"Provider info from registry: {provider_info}")
    supported_providers = []
    for provider_name, info in provider_info.items():
        supported_providers.append(
            {
                "value": provider_name,
                "label": info.label,
                "description": info.description,
            }
        )
        supported_providers = sorted(supported_providers, key=lambda x: str(x["value"]))
    logger.info(f"Supported providers for template: {supported_providers}")

    return _render_tab_with_nav(
        request,
        "partials/notifications/tab.html",
        "notifications",
        {
            "current_user": current_user,
            "supported_providers": supported_providers,
        },
    )


@router.get("/prune", response_class=HTMLResponse)
async def get_prune_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request, "partials/prune/tab.html", "prune", {"current_user": current_user}
    )


@router.get("/repository-check", response_class=HTMLResponse)
async def get_repository_check_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/repository_check/tab.html",
        "repository-check",
        {"current_user": current_user},
    )


@router.get("/packages", response_class=HTMLResponse)
async def get_packages_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request,
        "partials/packages/tab.html",
        "packages",
        {"current_user": current_user},
    )


@router.get("/debug", response_class=HTMLResponse)
async def get_debug_tab(
    request: Request, current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    return _render_tab_with_nav(
        request, "partials/debug/tab.html", "debug", {"current_user": current_user}
    )
