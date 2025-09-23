import random
import time
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from borgitory.dependencies import get_templates, ScheduleServiceDep


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


@router.get("/toggle-hooks-section", response_class=HTMLResponse)
async def toggle_hooks_section(
    request: Request,
    expanded: str = Query(
        ..., description="Whether hooks section is currently expanded"
    ),
) -> HTMLResponse:
    """Toggle hooks section expansion via HTMX."""
    is_expanded = expanded.lower() == "true"
    new_expanded = not is_expanded

    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks_section.html",
        {"expanded": new_expanded},
    )


@router.get("/toggle-hooks-edit-section", response_class=HTMLResponse)
async def toggle_hooks_edit_section(
    request: Request,
    schedule_service: ScheduleServiceDep,
    expanded: str = Query(
        ..., description="Whether hooks section is currently expanded"
    ),
    schedule_id: int = Query(..., description="Schedule ID for edit mode"),
) -> HTMLResponse:
    """Toggle hooks edit section expansion via HTMX."""
    is_expanded = expanded.lower() == "true"
    new_expanded = not is_expanded

    schedule = schedule_service.get_schedule_by_id(schedule_id)

    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks_edit_section.html",
        {"expanded": new_expanded, "schedule": schedule},
    )


@router.post("/add-hook-field", response_class=HTMLResponse)
async def add_hook_field(
    request: Request,
) -> HTMLResponse:
    """Add a new hook field row via HTMX."""

    unique_id = int(time.time() * 1000) + random.randint(0, 999)

    try:
        json_data = await request.json()
        hook_type = json_data.get("hook_type", "pre")
    except (ValueError, TypeError, KeyError):
        hook_type = "pre"

    return templates.TemplateResponse(
        request,
        "partials/schedules/hook_field_row.html",
        {"hook_type": hook_type, "index": unique_id},
    )


@router.delete("/remove-hook-field", response_class=HTMLResponse)
async def remove_hook_field() -> HTMLResponse:
    """Remove a hook field row via HTMX."""
    return HTMLResponse(content="", status_code=200)
