import logging
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.utils.security import get_or_generate_secret_key
from app.models.database import init_db, get_db
from app.api import (
    repositories,
    jobs,
    auth,
    schedules,
    sync,
    cloud_sync,
    cleanup,
    backups,
    notifications,
    debug,
    repository_stats,
    repository_check_configs,
    shared,
    tabs,
)
from app.dependencies import get_recovery_service, get_scheduler_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting Borgitory application...")

        from app.config import DATA_DIR

        if not os.getenv("SECRET_KEY"):
            secret_key = get_or_generate_secret_key(DATA_DIR)
            os.environ["SECRET_KEY"] = secret_key
            logger.info("SECRET_KEY initialized")

        await init_db()
        logger.info("Database initialized")

        recovery_service = get_recovery_service()
        await recovery_service.recover_stale_jobs()

        scheduler_service = get_scheduler_service()
        await scheduler_service.start()
        logger.info("Scheduler started")

        from app.services.archive_mount_manager import get_archive_mount_manager

        mount_manager = get_archive_mount_manager()

        import asyncio

        async def cleanup_task():
            while True:
                try:
                    await asyncio.sleep(300)  # 5 minutes
                    await mount_manager.cleanup_old_mounts()
                except Exception as e:
                    logger.error(f"Mount cleanup error: {e}")

        cleanup_task_handle = asyncio.create_task(cleanup_task())
        logger.info("Mount cleanup task started")

        yield

        logger.info("Shutting down...")

        cleanup_task_handle.cancel()
        try:
            await cleanup_task_handle
        except asyncio.CancelledError:
            pass

        await mount_manager.unmount_all()
        logger.info("All mounts cleaned up")

        await scheduler_service.stop()
    except Exception as e:
        logger.error(f"Lifespan error: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


app = FastAPI(title="Borgitory - BorgBackup Web Manager", lifespan=lifespan)


if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
else:
    logger.warning(
        "Static directory 'app/static' not found - static files will not be served"
    )

templates = Jinja2Templates(directory="app/templates")

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
    sync.router,
    prefix="/api/sync",
    tags=["sync"],
)

app.include_router(
    cloud_sync.router,
    prefix="/api/cloud-sync",
    tags=["cloud-sync"],
)

app.include_router(
    cleanup.router,
    prefix="/api/cleanup",
    tags=["cleanup"],
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

app.include_router(debug.router)


def _render_page_with_tab(request: Request, current_user, active_tab: str, initial_content_url: str):
    """Helper to render the main page with a specific tab active."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "current_user": current_user,
            "active_tab": active_tab,
            "initial_content_url": initial_content_url
        }
    )


@app.get("/")
async def root(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)

    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "repositories", "/api/tabs/repositories")


# Page routes for direct tab navigation
@app.get("/repositories")
async def repositories_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "repositories", "/api/tabs/repositories")


@app.get("/backups")
async def backups_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "backups", "/api/tabs/backups")


@app.get("/schedules")
async def schedules_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "schedules", "/api/tabs/schedules")


@app.get("/cloud-sync")
async def cloud_sync_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "cloud-sync", "/api/tabs/cloud-sync")


@app.get("/archives")
async def archives_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "archives", "/api/tabs/archives")


@app.get("/statistics")
async def statistics_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "statistics", "/api/tabs/statistics")


@app.get("/jobs")
async def jobs_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "jobs", "/api/tabs/jobs")


@app.get("/notifications")
async def notifications_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "notifications", "/api/tabs/notifications")


@app.get("/cleanup")
async def cleanup_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "cleanup", "/api/tabs/cleanup")


@app.get("/repository-check")
async def repository_check_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "repository-check", "/api/tabs/repository-check")


@app.get("/debug")
async def debug_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    return _render_page_with_tab(request, current_user, "debug", "/api/tabs/debug")


@app.get("/login")
async def login_page(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    from app.api.auth import get_current_user_optional

    current_user = get_current_user_optional(request, db)

    if current_user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(request, "login.html", {})
