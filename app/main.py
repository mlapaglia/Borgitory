import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.database import init_db
from app.api import repositories, jobs, auth, schedules, sync, cloud_backup, cleanup, notifications
from app.services.scheduler_service import scheduler_service
from app.services.recovery_service import recovery_service

# Configure logging to show container output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting Borgitory application...")
        await init_db()
        logger.info("Database initialized")
        
        # Recover any interrupted backup jobs from previous shutdown/crash
        await recovery_service.recover_stale_jobs()
        
        await scheduler_service.start()
        logger.info("Scheduler started")
        yield
        logger.info("Shutting down...")
        await scheduler_service.stop()
    except Exception as e:
        logger.error(f"Lifespan error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


app = FastAPI(title="Borgitory - BorgBackup Web Manager", lifespan=lifespan)

# Mount static files if directory exists
import os
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
else:
    logger.warning("Static directory 'app/static' not found - static files will not be served")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(repositories.router, prefix="/api/repositories", tags=["repositories"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(cloud_backup.router, prefix="/api/cloud-backup", tags=["cloud-backup"])
app.include_router(cleanup.router, prefix="/api/cleanup", tags=["cleanup"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])


@app.get("/")
async def root(request: Request):
    from fastapi.responses import HTMLResponse, RedirectResponse
    from app.api.auth import get_current_user_optional
    from app.models.database import get_db
    
    # Check if user is authenticated
    db = next(get_db())
    current_user = get_current_user_optional(request, db)
    
    if not current_user:
        # Redirect to login if not authenticated
        return RedirectResponse(url="/login", status_code=302)
    
    return templates.TemplateResponse("index.html", {"request": request, "current_user": current_user})


@app.get("/login")
async def login_page(request: Request):
    from fastapi.responses import HTMLResponse, RedirectResponse
    from app.api.auth import get_current_user_optional
    from app.models.database import get_db
    
    # Check if user is already authenticated
    db = next(get_db())
    current_user = get_current_user_optional(request, db)
    
    if current_user:
        # Redirect to main app if already logged in
        return RedirectResponse(url="/", status_code=302)
    
    return templates.TemplateResponse("login.html", {"request": request})


