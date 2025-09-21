from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session
import asyncio
from typing import Dict, AsyncGenerator

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


@router.get("/stats/content")
async def get_stats_content(
    request: Request,
    stats_svc: RepositoryStatsServiceDep,
    repository_id: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get statistics content based on repository selection"""
    if not repository_id or repository_id == "":
        return templates.TemplateResponse(
            request, "partials/statistics/empty_state.html", {}
        )

    try:
        repo_id = int(repository_id)
        # Redirect to the existing stats HTML endpoint
        return await get_repository_statistics_html(repo_id, request, stats_svc, db)
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            request, "partials/statistics/empty_state.html", {}
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


@router.get("/{repository_id}/stats/progress")
async def get_repository_statistics_progress(
    repository_id: int,
    request: Request,
    stats_svc: RepositoryStatsServiceDep,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream repository statistics generation progress via Server-Sent Events"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    async def generate_progress() -> AsyncGenerator[str, None]:
        progress_queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue()

        def progress_callback(message: str, percent: int = 0) -> None:
            # Put progress data in queue (non-blocking)
            try:
                progress_data = {"message": message, "percent": percent}
                progress_queue.put_nowait(progress_data)
            except asyncio.QueueFull:
                pass  # Skip if queue is full

        # Start stats generation in background
        stats_task = asyncio.create_task(
            stats_svc.get_repository_statistics(repository, db, progress_callback)
        )

        try:
            while not stats_task.done():
                try:
                    # Wait for progress data with timeout
                    progress_data = await asyncio.wait_for(
                        progress_queue.get(), timeout=0.5
                    )

                    # Send progress message
                    yield f"event: progress\ndata: {progress_data['message']}\n\n"

                    # Send progress bar update if percentage is provided
                    if progress_data["percent"] is not None:
                        progress_bar_html = f'<div class="bg-blue-600 h-2 rounded-full transition-all duration-500" style="width: {progress_data["percent"]}%"></div>'
                        yield f"event: progress-bar\ndata: {progress_bar_html}\n\n"

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield "event: heartbeat\ndata: ping\n\n"
                    continue

            # Get the final result
            stats = await stats_task

            if "error" in stats:
                yield f"event: error\ndata: <p class='text-red-700 dark:text-red-300 text-sm text-center'>{stats['error']}</p>\n\n"
            else:
                # Send completion signal - HTMX element with sse-swap="complete" will trigger
                yield "event: complete\ndata: done\n\n"

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@router.get("/{repository_id}/stats/html")
async def get_repository_statistics_html(
    repository_id: int,
    request: Request,
    stats_svc: RepositoryStatsServiceDep,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get repository statistics as HTML partial"""

    templates = get_templates()

    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    stats = await stats_svc.get_repository_statistics(repository, db)

    return templates.TemplateResponse(
        request,
        "partials/repository_stats/stats_panel.html",
        {"repository": repository, "stats": stats},
    )
