import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.api.auth import get_current_user
from borgitory.dependencies import DebugServiceDep, get_db, get_templates

router = APIRouter(
    prefix="/api/debug",
    tags=["debug"],
    dependencies=[Depends(get_current_user)],
)
templates = get_templates()
logger = logging.getLogger(__name__)


@router.get("/info", response_model=None)
async def get_debug_info(
    debug_svc: DebugServiceDep, db: AsyncSession = Depends(get_db)
) -> Any:
    """Get comprehensive debug information"""
    try:
        debug_info = await debug_svc.get_debug_info(db)
        return debug_info
    except Exception as e:
        logger.exception("Failed to collect debug info")
        raise HTTPException(
            status_code=500, detail="Failed to collect debug info"
        ) from e


@router.get("/html", response_class=HTMLResponse)
async def get_debug_html(
    request: Request, debug_svc: DebugServiceDep, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Get debug information as HTML"""
    try:
        debug_info = await debug_svc.get_debug_info(db)
        return templates.TemplateResponse(
            request,
            "partials/debug/debug_panel.html",
            {"debug_info": debug_info},
        )
    except Exception as e:
        logger.exception("Failed to collect debug info")
        raise HTTPException(
            status_code=500, detail="Failed to collect debug info"
        ) from e
