from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from borgitory.dependencies import get_templates

router = APIRouter()
templates = get_templates()


@router.get("/notification", response_class=HTMLResponse)
async def get_notification(
    request: Request,
    message: str,
    type: str = "info",
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
async def remove_notification() -> HTMLResponse:
    """Remove a notification (returns empty content)."""
    return HTMLResponse(content="", status_code=200)
