import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi import Request
from sqlalchemy.orm import Session

from borgitory.models.database import get_db
from borgitory.dependencies import DebugServiceDep, get_templates
from borgitory.services.debug_service import DebugInfo

router = APIRouter(prefix="/api/debug", tags=["debug"])
templates = get_templates()
logger = logging.getLogger(__name__)


@router.get("/info")
async def get_debug_info(
    debug_svc: DebugServiceDep, db: Session = Depends(get_db)
) -> DebugInfo:
    """Get comprehensive debug information"""
    try:
        debug_info = await debug_svc.get_debug_info(db)
        return debug_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/html", response_class=HTMLResponse)
async def get_debug_html(
    request: Request, debug_svc: DebugServiceDep, db: Session = Depends(get_db)
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
        raise HTTPException(status_code=500, detail=str(e))
