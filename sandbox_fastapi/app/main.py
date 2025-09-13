"""
Clean FastAPI Sandbox - Proof of Concept for Repository Import

This demonstrates proper FastAPI dependency injection and clean architecture
without the complexity of the legacy system.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from app.api.repositories import router as repository_router
from app.api.jobs import router as jobs_router
from app.api.backups import router as backups_router
from app.api.notifications import router as notifications_router
from app.dependencies import RepositoryManagementServiceDep, DatabaseDep, TemplatesDep

logger = logging.getLogger(__name__)

# Create clean FastAPI app with comprehensive configuration
app = FastAPI(
    title="Repository Manager Sandbox",
    description="""
    Clean Architecture Proof of Concept
    
    This application demonstrates:
    * Clean FastAPI dependency injection with Annotated[Service, Depends()]
    * SQLAlchemy 2.0 with proper type hints and session management
    * Alembic migrations with naming conventions
    * Service layer architecture with single responsibility principle
    * Comprehensive input validation and security
    * Proper error handling and logging
    * Test-driven development with dependency overrides
    """,
    version="1.0.0",
    contact={
        "name": "Clean Architecture Reference",
        "url": "https://github.com/example/clean-architecture"
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# Template setup

# Include routers
app.include_router(repository_router, prefix="/api/repositories", tags=["repositories"])
app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
app.include_router(backups_router, prefix="/api/backups", tags=["backups"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])

@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    templates: TemplatesDep,
    repository_service: RepositoryManagementServiceDep,
    db: DatabaseDep
):
    """
    Main page showing repository list using proper FastAPI dependency injection.
    
    FIXED: Now uses proper FastAPI DI instead of manual service instantiation.
    """
    repositories = []
    try:
        repositories = repository_service.list_repositories(db, 0, 100)
    except Exception as e:
        # Use proper logging instead of print
        logger.error(f"Error loading repositories for main page: {e}")
    
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "Repository Manager - Clean Architecture",
            "repositories": repositories
        }
    )

