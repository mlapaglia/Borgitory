from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.api.auth import get_current_user
from app.models.database import User
from app.dependencies import TemplatesDep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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


@router.get("/select-path", response_class=HTMLResponse)
async def select_path(
    request: Request,
    path: str,
    target_input: str,
    templates: TemplatesDep,
    current_user: User = Depends(get_current_user)
) -> HTMLResponse:
    """Handle path selection - updates input value and triggers new search if needed."""
    
    # Return a response that updates the input value and optionally triggers new search
    return templates.TemplateResponse(
        request,
        "partials/shared/path_selection_response.html",
        {
            "path": path,
            "target_input": target_input,
            "should_search": path.endswith('/')  # Search again if it's a directory
        }
    )


