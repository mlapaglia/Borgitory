from typing import Dict, Any, List
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from borgitory.dependencies import get_templates, ScheduleServiceDep, TemplatesDep
import json
import html
import logging

router = APIRouter()
templates = get_templates()
logger = logging.getLogger(__name__)


def _extract_hooks_from_form(form_data: Any, hook_type: str) -> List[Dict[str, str]]:
    """Extract hooks from form data and return as list of dicts."""
    hooks = []

    # Get all names and commands for this hook type
    hook_names = form_data.getlist(f"{hook_type}_hook_name")
    hook_commands = form_data.getlist(f"{hook_type}_hook_command")

    logger.info(f"_extract_hooks_from_form - hook_type: {hook_type}")
    logger.info(f"_extract_hooks_from_form - {hook_type}_hook_name: {hook_names}")
    logger.info(f"_extract_hooks_from_form - {hook_type}_hook_command: {hook_commands}")

    # Pair them up by position
    for i in range(min(len(hook_names), len(hook_commands))):
        name = str(hook_names[i]).strip() if hook_names[i] else ""
        command = str(hook_commands[i]).strip() if hook_commands[i] else ""

        # Add all hooks, even if name or command is empty (for reordering)
        hooks.append({"name": name, "command": command})

    logger.info(f"_extract_hooks_from_form - extracted {len(hooks)} hooks: {hooks}")
    return hooks


def _convert_hook_fields_to_json(form_data: Any, hook_type: str) -> str | None:
    """Convert individual hook fields to JSON format using position-based form data."""
    hooks = _extract_hooks_from_form(form_data, hook_type)

    # Filter out hooks that don't have both name and command for JSON output
    valid_hooks = [hook for hook in hooks if hook["name"] and hook["command"]]

    return json.dumps(valid_hooks) if valid_hooks else None


def _validate_hooks_for_save(form_data: Any) -> tuple[bool, str | None]:
    """Validate that all hooks have both name and command filled out."""
    errors = []

    # Check pre-hooks
    pre_hooks = _extract_hooks_from_form(form_data, "pre")
    for i, hook in enumerate(pre_hooks):
        if not hook["name"].strip() and not hook["command"].strip():
            # Empty hook - skip (will be filtered out)
            continue
        elif not hook["name"].strip():
            errors.append(f"Pre-hook #{i + 1}: Hook name is required")
        elif not hook["command"].strip():
            errors.append(f"Pre-hook #{i + 1}: Hook command is required")

    # Check post-hooks
    post_hooks = _extract_hooks_from_form(form_data, "post")
    for i, hook in enumerate(post_hooks):
        if not hook["name"].strip() and not hook["command"].strip():
            # Empty hook - skip (will be filtered out)
            continue
        elif not hook["name"].strip():
            errors.append(f"Post-hook #{i + 1}: Hook name is required")
        elif not hook["command"].strip():
            errors.append(f"Post-hook #{i + 1}: Hook command is required")

    if errors:
        return False, "; ".join(errors)
    return True, None


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
    templates: TemplatesDep,
) -> HTMLResponse:
    """Add a new hook field row via HTMX."""

    # Get form data (includes both hx-vals and hx-include data)
    form_data = await request.form()

    # Get hook_type from form data (sent via hx-vals)
    hook_type = str(form_data.get("hook_type", "pre"))

    logger.info(f"Add hook field - hook_type: {hook_type}")

    # Debug: log all form fields
    logger.info(f"Add hook field - form_data keys: {list(form_data.keys())}")
    for key in form_data.keys():
        if "hook" in key:
            logger.info(f"Add hook field - {key}: {form_data.getlist(key)}")

    current_hooks = _extract_hooks_from_form(form_data, hook_type)

    # Add a new empty hook
    current_hooks.append({"name": "", "command": ""})

    logger.info(
        f"Add hook field - extracted {len(current_hooks) - 1} existing {hook_type} hooks, total after add: {len(current_hooks)}"
    )

    # Return updated container with all hooks (including the new one)
    return templates.TemplateResponse(
        request,
        "partials/shared/hooks_container.html",
        {"hook_type": hook_type, "hooks": current_hooks},
    )


@router.post("/move-hook-up", response_class=HTMLResponse)
async def move_hook_up(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Move a hook up in the list and return updated container."""
    form_data = await request.form()

    try:
        # Get move parameters
        hook_type = str(form_data.get("hook_type", "pre"))
        index = int(str(form_data.get("index", "0")))

        logger.info(f"Move hook up - hook_type: {hook_type}, index: {index}")

        # Get current hooks from form data
        current_hooks = _extract_hooks_from_form(form_data, hook_type)

        # Move hook up (swap with previous)
        if index > 0 and index < len(current_hooks):
            current_hooks[index], current_hooks[index - 1] = (
                current_hooks[index - 1],
                current_hooks[index],
            )

        logger.info(f"Move hook up - reordered hooks: {current_hooks}")

        # Return updated container
        return templates.TemplateResponse(
            request,
            "partials/shared/hooks_container.html",
            {"hook_type": hook_type, "hooks": current_hooks},
        )

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Move hook up error: {e}")
        # Return empty container on error
        return HTMLResponse(content='<div class="space-y-4"></div>')


@router.post("/move-hook-down", response_class=HTMLResponse)
async def move_hook_down(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Move a hook down in the list and return updated container."""
    form_data = await request.form()

    try:
        # Get move parameters
        hook_type = str(form_data.get("hook_type", "pre"))
        index = int(str(form_data.get("index", "0")))

        logger.info(f"Move hook down - hook_type: {hook_type}, index: {index}")

        # Get current hooks from form data
        current_hooks = _extract_hooks_from_form(form_data, hook_type)

        # Move hook down (swap with next)
        if index >= 0 and index < len(current_hooks) - 1:
            current_hooks[index], current_hooks[index + 1] = (
                current_hooks[index + 1],
                current_hooks[index],
            )

        logger.info(f"Move hook down - reordered hooks: {current_hooks}")

        # Return updated container
        return templates.TemplateResponse(
            request,
            "partials/shared/hooks_container.html",
            {"hook_type": hook_type, "hooks": current_hooks},
        )

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Move hook down error: {e}")
        # Return empty container on error
        return HTMLResponse(content='<div class="space-y-4"></div>')


@router.post("/remove-hook-field", response_class=HTMLResponse)
async def remove_hook_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Remove a hook field row via HTMX."""

    # Get form data (includes both hx-vals and hx-include data)
    form_data = await request.form()

    # Get parameters
    hook_type = str(form_data.get("hook_type", "pre"))
    index_to_remove = int(str(form_data.get("index", "0")))

    logger.info(f"Remove hook field - hook_type: {hook_type}, index: {index_to_remove}")

    # Get current hooks from form data
    current_hooks = _extract_hooks_from_form(form_data, hook_type)

    # Remove the hook at the specified index
    if 0 <= index_to_remove < len(current_hooks):
        removed_hook = current_hooks.pop(index_to_remove)
        logger.info(f"Remove hook field - removed hook: {removed_hook}")
    else:
        logger.warning(
            f"Remove hook field - invalid index {index_to_remove} for {len(current_hooks)} hooks"
        )

    logger.info(f"Remove hook field - remaining hooks: {len(current_hooks)}")

    # Return updated container with remaining hooks
    return templates.TemplateResponse(
        request,
        "partials/shared/hooks_container.html",
        {"hook_type": hook_type, "hooks": current_hooks},
    )


@router.post("/hooks-modal", response_class=HTMLResponse)
async def get_hooks_modal(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Open hooks configuration modal with current hook data passed from parent."""
    # Get JSON data from hx-vals
    import logging

    logger = logging.getLogger(__name__)

    try:
        json_data = await request.json()
        logger.info(f"Modal opening - json_data: {json_data}")

        # Get hooks data passed from parent component
        pre_hooks_json = str(json_data.get("pre_hooks", "[]"))
        post_hooks_json = str(json_data.get("post_hooks", "[]"))
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Failed to parse JSON data: {e}")
        pre_hooks_json = "[]"
        post_hooks_json = "[]"

    logger.info(f"Modal opening - pre_hooks_json: {pre_hooks_json}")
    logger.info(f"Modal opening - post_hooks_json: {post_hooks_json}")

    # Parse JSON to hook objects for rendering
    try:
        pre_hooks = (
            json.loads(pre_hooks_json)
            if pre_hooks_json and pre_hooks_json != "[]"
            else []
        )
        post_hooks = (
            json.loads(post_hooks_json)
            if post_hooks_json and post_hooks_json != "[]"
            else []
        )
        logger.info(f"Parsed pre_hooks: {pre_hooks}")
        logger.info(f"Parsed post_hooks: {post_hooks}")
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSON parsing error: {e}")
        pre_hooks = []
        post_hooks = []

    return templates.TemplateResponse(
        request,
        "partials/shared/hooks_modal.html",
        {
            "pre_hooks": pre_hooks,
            "post_hooks": post_hooks,
            "pre_hooks_json": pre_hooks_json,
            "post_hooks_json": post_hooks_json,
        },
    )


@router.post("/save-hooks", response_class=HTMLResponse)
async def save_hooks(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Save hooks configuration and update parent component via OOB swap."""
    form_data = await request.form()

    # Validate hooks before saving
    is_valid, error_message = _validate_hooks_for_save(form_data)
    if not is_valid:
        # Return error response
        return HTMLResponse(
            content=f"""
            <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4 mb-4">
                <div class="flex">
                    <svg class="w-5 h-5 text-red-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                    </svg>
                    <div class="ml-3">
                        <h3 class="text-sm font-medium text-red-800 dark:text-red-200">Validation Error</h3>
                        <p class="mt-1 text-sm text-red-700 dark:text-red-300">{error_message}</p>
                    </div>
                </div>
            </div>
            """,
            status_code=400,
        )

    # Convert hook fields to JSON
    pre_hooks_json = _convert_hook_fields_to_json(form_data, "pre")
    post_hooks_json = _convert_hook_fields_to_json(form_data, "post")

    # Debug logging for save
    logger.info(f"Save hooks - form_data keys: {list(form_data.keys())}")

    # Log all form fields to see what's being submitted
    for key in form_data.keys():
        if "hook" in key:
            logger.info(f"Save hooks - {key}: {form_data.getlist(key)}")

    logger.info(f"Save hooks - pre_hooks_json: {pre_hooks_json}")
    logger.info(f"Save hooks - post_hooks_json: {post_hooks_json}")

    # Count hooks for display
    try:
        pre_count = len(json.loads(pre_hooks_json)) if pre_hooks_json else 0
        post_count = len(json.loads(post_hooks_json)) if post_hooks_json else 0
    except (json.JSONDecodeError, TypeError):
        pre_count = 0
        post_count = 0

    total_count = pre_count + post_count
    logger.info(f"Save hooks - total_count: {total_count}")

    # Return simple HTML response with OOB updates
    response_html = f"""
    <!-- Close the modal -->
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    
    <!-- Update the hooks display section -->
    <div id="hooks-display-section" hx-swap-oob="outerHTML">
        <button type="button" 
                class="flex items-center space-x-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 focus:ring-2 focus:ring-blue-500 transition-colors"
                hx-post="/api/shared/hooks-modal"
                hx-vals='{{"pre_hooks": {json.dumps(pre_hooks_json or "")}, "post_hooks": {json.dumps(post_hooks_json or "")}}}'
                hx-target="#modal-container">
            <span>⚙️</span>
            <span>Configure Pre/Post Job Hooks</span>
            {f'<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">{total_count}</span>' if total_count > 0 else ""}
        </button>
        
        <!-- Hidden fields for form submission -->
        <input type="hidden" name="pre_job_hooks" id="pre-hooks-data" value="{html.escape(pre_hooks_json or "")}">
        <input type="hidden" name="post_job_hooks" id="post-hooks-data" value="{html.escape(post_hooks_json or "")}">
    </div>
    """

    return HTMLResponse(content=response_html)


@router.get("/close-modal", response_class=HTMLResponse)
async def close_modal() -> HTMLResponse:
    """Close modal without saving."""
    return HTMLResponse(content='<div id="modal-container"></div>', status_code=200)
