from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, Repository
from app.services.repository_stats_service import repository_stats_service

router = APIRouter()


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
async def get_repository_statistics_html(repository_id: int, request: Request, db: Session = Depends(get_db)):
    """Get repository statistics as HTML partial"""
    from fastapi.templating import Jinja2Templates
    
    templates = Jinja2Templates(directory="app/templates")

    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    stats = await repository_stats_service.get_repository_statistics(repository, db)
    
    return templates.TemplateResponse(
        "partials/repository_stats/stats_panel.html",
        {"request": request, "repository": repository, "stats": stats}
    )