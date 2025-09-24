from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from borgitory.api.cancel_on_disconnect import with_cancel_on_disconnect
from borgitory.models.database import get_db, Repository
from borgitory.dependencies import RepositoryStatsServiceDep, get_templates
from borgitory.services.repositories.repository_stats_service import RepositoryStats

router = APIRouter()
templates = get_templates()


@router.get("/stats/selector")
async def get_stats_repository_selector(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Get repository selector with repositories populated for statistics"""
    repositories = db.query(Repository).all()

    return templates.TemplateResponse(
        request,
        "partials/statistics/repository_selector.html",
        {"repositories": repositories},
    )


@router.get("/stats/loading")
async def get_stats_loading(request: Request, repository_id: int = 0) -> HTMLResponse:
    """Get loading state for statistics with SSE connection"""
    return templates.TemplateResponse(
        request,
        "partials/statistics/loading_state.html",
        {"repository_id": repository_id},
    )


@router.get("/{repository_id}/stats")
async def get_repository_statistics(
    repository_id: int,
    stats_svc: RepositoryStatsServiceDep,
    db: Session = Depends(get_db),
) -> RepositoryStats:
    """Get comprehensive repository statistics"""

    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    stats = await stats_svc.get_repository_statistics(repository, db)

    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])

    return stats


@router.get("/{repository_id}/stats/html")
@with_cancel_on_disconnect
async def get_repository_statistics_html(
    repository_id: int,
    request: Request,
    stats_svc: RepositoryStatsServiceDep,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get repository statistics as HTML partial with cancellation support"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Generate statistics (no timeout for now)
    stats = await stats_svc.get_repository_statistics(repository, db)

    if "error" in stats:
        return HTMLResponse(
            content=f"<p class='text-red-700 dark:text-red-300 text-sm text-center'>{stats['error']}</p>",
            status_code=500,
        )

    return templates.TemplateResponse(
        request,
        "partials/repository_stats/stats_panel.html",
        {"repository": repository, "stats": stats},
    )
