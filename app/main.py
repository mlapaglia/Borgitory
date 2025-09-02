import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.database import init_db
from app.api import repositories, jobs, auth, schedules, sync, cloud_backup
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
        print("🔥 LIFESPAN: Starting Borgitory application...")
        logger.info("🔥 STARTING Borgitory application...")
        await init_db()
        print("🔥 LIFESPAN: Database initialized")
        logger.info("🔥 Database initialized")
        
        # Recover any interrupted backup jobs from previous shutdown/crash
        print("🔥 LIFESPAN: About to start recovery...")
        logger.info("🔥 About to start recovery...")
        await recovery_service.recover_stale_jobs()
        print("🔥 LIFESPAN: Recovery completed")
        logger.info("🔥 Recovery completed")
        
        await scheduler_service.start()
        print("🔥 LIFESPAN: Scheduler started")
        logger.info("🔥 Scheduler started")
        yield
        print("🔥 LIFESPAN: Shutting down...")
        logger.info("🔥 Shutting down...")
        await scheduler_service.stop()
    except Exception as e:
        print(f"🔥 LIFESPAN ERROR: {e}")
        logger.error(f"🔥 LIFESPAN ERROR: {e}")
        import traceback
        print(f"🔥 TRACEBACK: {traceback.format_exc()}")
        logger.error(f"🔥 TRACEBACK: {traceback.format_exc()}")
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


