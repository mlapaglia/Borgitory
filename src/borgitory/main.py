import logging
import os
import sys
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.templating import _TemplateResponse
from borgitory.models.database import User
from borgitory.utils.template_paths import get_static_directory, get_template_directory
from borgitory.utils.security import get_or_generate_secret_key
from borgitory.models.database import init_db, get_db
from borgitory.api import (
    repositories,
    jobs,
    auth,
    schedules,
    cloud_sync,
    backups,
    notifications,
    debug,
    prune,
    repository_stats,
    repository_check_configs,
    shared,
    tabs,
    packages,
)
from borgitory.dependencies import (
    get_archive_mount_manager_singleton,
    get_recovery_service,
    get_scheduler_service_singleton,
    get_package_restoration_service_for_startup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        logger.info("Starting Borgitory application...")

        from borgitory.config_module import DATA_DIR

        secret_key = get_or_generate_secret_key(DATA_DIR)
        os.environ["SECRET_KEY"] = secret_key
        logger.info("SECRET_KEY initialized")

        await init_db()
        logger.info("Database initialized")

        try:
            restoration_service = get_package_restoration_service_for_startup()
            await restoration_service.restore_user_packages()
        except Exception as e:
            logger.error(f"Package restoration failed during startup: {e}")

        recovery_service = get_recovery_service()
        await recovery_service.recover_stale_jobs()

        scheduler_service = get_scheduler_service_singleton()
        await scheduler_service.start()
        logger.info("Scheduler started")

        mount_manager = get_archive_mount_manager_singleton()

        yield

        logger.info("Shutting down...")

        await mount_manager.unmount_all()
        logger.info("All mounts cleaned up")

        await scheduler_service.stop()
    except Exception as e:
        logger.error(f"Lifespan error: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


app = FastAPI(title="Borgitory - BorgBackup Web Manager", lifespan=lifespan)

static_path = get_static_directory()
template_path = get_template_directory()

logger.info(f"Resolved paths - static: {static_path}, template: {template_path}")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
else:
    logger.warning(
        f"Static directory '{static_path}' not found - static files will not be served"
    )

templates = Jinja2Templates(directory=template_path)

app.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    repositories.router,
    prefix="/api/repositories",
    tags=["repositories"],
)

app.include_router(
    repository_stats.router,
    prefix="/api/repositories",
    tags=["repository-stats"],
)

app.include_router(
    jobs.router,
    prefix="/api/jobs",
    tags=["jobs"],
)

app.include_router(
    schedules.router,
    prefix="/api/schedules",
    tags=["schedules"],
)


app.include_router(
    cloud_sync.router,
    prefix="/api/cloud-sync",
    tags=["cloud-sync"],
)

app.include_router(
    prune.router,
    prefix="/api/prune",
    tags=["prune"],
)

app.include_router(
    backups.router,
    prefix="/api/backups",
    tags=["backups"],
)

app.include_router(
    repository_check_configs.router,
    prefix="/api/repository-check-configs",
    tags=["repository-check-configs"],
)

app.include_router(
    notifications.router,
    prefix="/api/notifications",
    tags=["notifications"],
)

app.include_router(
    shared.router,
    prefix="/api/shared",
    tags=["shared"],
)

app.include_router(
    tabs.router,
    prefix="/api/tabs",
    tags=["tabs"],
)

app.include_router(
    packages.router,
    prefix="/api/packages",
    tags=["packages"],
)

app.include_router(debug.router)


# Valid tab pages and their corresponding API endpoints
VALID_TABS = {
    "repositories": "/api/tabs/repositories",
    "backups": "/api/tabs/backups",
    "schedules": "/api/tabs/schedules",
    "cloud-sync": "/api/tabs/cloud-sync",
    "archives": "/api/tabs/archives",
    "statistics": "/api/tabs/statistics",
    "jobs": "/api/tabs/jobs",
    "notifications": "/api/tabs/notifications",
    "packages": "/api/tabs/packages",
    "prune": "/api/tabs/prune",
    "repository-check": "/api/tabs/repository-check",
    "debug": "/api/tabs/debug",
}


def _render_page_with_tab(
    request: Request, current_user: User, active_tab: str, initial_content_url: str
) -> _TemplateResponse:
    """Helper to render the main page with a specific tab active."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "current_user": current_user,
            "active_tab": active_tab,
            "initial_content_url": initial_content_url,
        },
    )


@app.get("/")
async def root(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    current_user = auth.get_current_user_optional(request, db)

    if not current_user:
        return RedirectResponse(url="/login?next=/repositories", status_code=302)

    # Redirect to repositories tab
    return RedirectResponse(url="/repositories", status_code=302)


@app.get("/login", response_model=None)
async def login_page(
    request: Request, db: Session = Depends(get_db)
) -> RedirectResponse | _TemplateResponse:
    current_user = auth.get_current_user_optional(request, db)
    next_url = request.query_params.get("next", "/repositories")
    # Strip backslashes, and validate redirect target is internal
    cleaned_next_url = next_url.replace("\\", "")
    parsed_url = urlparse(cleaned_next_url)
    safe_next_url = (
        cleaned_next_url
        if not parsed_url.scheme and not parsed_url.netloc
        else "/repositories"
    )

    if current_user:
        return RedirectResponse(url=safe_next_url, status_code=302)

    return templates.TemplateResponse(request, "login.html", {"next": safe_next_url})


# Dynamic route for all tab pages
@app.get("/{tab_name}", response_model=None)
async def tab_page(
    tab_name: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse | _TemplateResponse:
    from fastapi.responses import RedirectResponse
    from fastapi import HTTPException
    from borgitory.api.auth import get_current_user_optional

    if tab_name not in VALID_TABS:
        raise HTTPException(status_code=404, detail="Page not found")

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url=f"/login?next=/{tab_name}", status_code=302)

    return _render_page_with_tab(request, current_user, tab_name, VALID_TABS[tab_name])
