from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services.debug_service import debug_service

router = APIRouter(prefix="/api/debug", tags=["debug"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/info")
async def get_debug_info(db: Session = Depends(get_db)):
    """Get comprehensive debug information"""
    try:
        debug_info = await debug_service.get_debug_info(db)
        return debug_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/html", response_class=HTMLResponse)
async def get_debug_html(request: Request, db: Session = Depends(get_db)):
    """Get debug information as HTML"""
    try:
        debug_info = await debug_service.get_debug_info(db)
        return templates.TemplateResponse(
            "partials/debug/debug_panel.html",
            {"request": request, "debug_info": debug_info},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
