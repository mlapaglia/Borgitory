from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from api.auth import get_current_user
from models.database import User

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")


@router.get("/notification", response_class=HTMLResponse)
async def get_notification(
    request: Request, 
    message: str, 
    type: str = "info",
    current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    """Get a notification with specified message and type.

    Args:
        message: The notification message
        type: Notification type (success, error, warning, info)
    """
    context = {"message": message, "type": type}

    return templates.TemplateResponse(
        request, "partials/shared/notification.html", context
    )


@router.get("/notification-remove", response_class=HTMLResponse)
async def remove_notification(
    request: Request,
    current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    """Remove a notification (returns empty content)."""
    return HTMLResponse(content="", status_code=200)
