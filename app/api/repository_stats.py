from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, Repository
from app.services.repository_stats_service import repository_stats_service

router = APIRouter()

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")


@router.get("/stats/selector")
async def get_stats_repository_selector(request: Request, db: Session = Depends(get_db)):
    """Get repository selector with repositories populated for statistics"""
    repositories = db.query(Repository).all()
    
    return templates.TemplateResponse(
        "partials/statistics/repository_selector.html",
        {"request": request, "repositories": repositories}
    )


@router.get("/stats/loading")
async def get_stats_loading(request: Request):
    """Get loading state for statistics"""
    return templates.TemplateResponse(
        "partials/statistics/loading_state.html",
        {"request": request}
    )


@router.get("/stats/content")
async def get_stats_content(request: Request, repository_id: int = None, db: Session = Depends(get_db)):
    """Get statistics content based on repository selection"""
    if not repository_id:
        return templates.TemplateResponse(
            "partials/statistics/empty_state.html",
            {"request": request}
        )
    
    # Redirect to the existing stats HTML endpoint
    return await get_repository_statistics_html(repository_id, request, db)


@router.get("/{repository_id}/stats")
async def get_repository_statistics(repository_id: int, db: Session = Depends(get_db)):
    """Get comprehensive repository statistics"""

    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    stats = await repository_stats_service.get_repository_statistics(repository, db)

    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])

    return stats


@router.get("/{repository_id}/stats/html")
async def get_repository_statistics_html(
    repository_id: int, request: Request, db: Session = Depends(get_db)
):
    """Get repository statistics as HTML partial"""
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")

    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    stats = await repository_stats_service.get_repository_statistics(repository, db)

    return templates.TemplateResponse(
        "partials/repository_stats/stats_panel.html",
        {"request": request, "repository": repository, "stats": stats},
    )
