import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.database import init_db
from app.api import repositories, jobs, auth, schedules, sync
from app.services.scheduler_service import scheduler_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Borgitory application...")
    await init_db()
    logger.info("Database initialized")
    scheduler_service.start()
    logger.info("Scheduler started")
    yield
    logger.info("Shutting down...")
    scheduler_service.stop()


app = FastAPI(title="Borgitory - BorgBackup Web Manager", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(repositories.router, prefix="/api/repositories", tags=["repositories"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])


@app.get("/")
async def root():
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    return templates.TemplateResponse("index.html", {"request": request})


