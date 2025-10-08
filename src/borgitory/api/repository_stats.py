from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from borgitory.api.cancel_on_disconnect import with_cancel_on_disconnect
from borgitory.models.database import Repository
from borgitory.dependencies import get_db
from borgitory.dependencies import RepositoryStatsServiceDep, get_templates
from borgitory.services.repositories.repository_stats_service import RepositoryStats

router = APIRouter()
templates = get_templates()


@router.get("/stats/selector")
async def get_stats_repository_selector(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Get repository selector with repositories populated for statistics"""
    results = await db.execute(select(Repository))
    repositories = results.scalars().all()

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
    db: AsyncSession = Depends(get_db),
) -> RepositoryStats:
    """Get comprehensive repository statistics"""

    result = await db.execute(select(Repository).where(Repository.id == repository_id))
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        stats = await stats_svc.get_repository_statistics(repository, db)
        return stats
    except ValueError as e:
        # Handle validation errors (e.g., no archives found)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle other errors
        raise HTTPException(
            status_code=500, detail=f"Error generating statistics: {str(e)}"
        )


@router.get("/{repository_id}/stats/html")
@with_cancel_on_disconnect
async def get_repository_statistics_html(
    repository_id: int,
    request: Request,
    stats_svc: RepositoryStatsServiceDep,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get repository statistics as HTML partial with cancellation support"""
    result = await db.execute(select(Repository).where(Repository.id == repository_id))
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    try:
        # Generate statistics (no timeout for now)
        stats = await stats_svc.get_repository_statistics(repository, db)

        return templates.TemplateResponse(
            request,
            "partials/repository_stats/stats_panel.html",
            {"repository": repository, "stats": stats},
        )
    except ValueError as e:
        # Handle validation errors (e.g., no archives found)
        return HTMLResponse(
            content=f"<p class='text-red-700 dark:text-red-300 text-sm text-center'>{str(e)}</p>",
            status_code=400,
        )
    except Exception:
        # Handle other errors - log exception for diagnostics, return only generic info to user
        logging.exception(
            "Exception occurred while generating repository statistics HTML (repository_id=%s)",
            repository_id,
        )
        return HTMLResponse(
            content="<p class='text-red-700 dark:text-red-300 text-sm text-center'>An internal error has occurred while generating repository statistics.</p>",
            status_code=500,
        )
