from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse
from starlette.templating import _TemplateResponse
from sqlalchemy.orm import Session
from typing import cast, List, Dict, Any, Optional
import json

from borgitory.models.database import get_db
from borgitory.models.schemas import (
    ScheduleCreate,
    ScheduleUpdate,
)
from borgitory.dependencies import (
    SchedulerServiceDep,
    TemplatesDep,
    ScheduleServiceDep,
    ConfigurationServiceDep,
    UpcomingBackupsServiceDep,
)
from borgitory.services.cron_description_service import CronDescriptionService
from borgitory.models.patterns import BackupPattern, PatternType, PatternStyle
from borgitory.services.borg.borg_pattern_validation_service import validate_pattern

router = APIRouter()


def convert_hook_fields_to_json(
    form_data: Dict[str, Any], hook_type: str
) -> Optional[str]:
    """Convert individual hook fields to JSON format using position-based form data."""
    hooks = []

    # Get all hook field data for this hook type (position-based)
    hook_names = form_data.get(f"{hook_type}_hook_name", [])
    hook_commands = form_data.get(f"{hook_type}_hook_command", [])
    hook_critical = form_data.get(f"{hook_type}_hook_critical", [])
    hook_run_on_failure = form_data.get(f"{hook_type}_hook_run_on_failure", [])

    # Ensure they are lists (in case there's only one item)
    if not isinstance(hook_names, list):
        hook_names = [hook_names] if hook_names else []
    if not isinstance(hook_commands, list):
        hook_commands = [hook_commands] if hook_commands else []
    if not isinstance(hook_critical, list):
        hook_critical = [hook_critical] if hook_critical else []
    if not isinstance(hook_run_on_failure, list):
        hook_run_on_failure = [hook_run_on_failure] if hook_run_on_failure else []

    # Pair them up by position
    for i in range(min(len(hook_names), len(hook_commands))):
        name = str(hook_names[i]).strip() if hook_names[i] else ""
        command = str(hook_commands[i]).strip() if hook_commands[i] else ""

        # Handle checkboxes - they're only present if checked
        critical = len(hook_critical) > i and hook_critical[i] == "true"
        run_on_failure = (
            len(hook_run_on_failure) > i and hook_run_on_failure[i] == "true"
        )

        # Only add hooks that have both name and command
        if name and command:
            hooks.append(
                {
                    "name": name,
                    "command": command,
                    "critical": critical,
                    "run_on_job_failure": run_on_failure,
                }
            )

    return json.dumps(hooks) if hooks else None


def convert_patterns_from_form_data(form_data: Dict[str, Any]) -> Optional[str]:
    """Convert patterns form data to JSON format."""
    patterns = []

    # Get all pattern field data (position-based)
    pattern_names = form_data.get("pattern_name", [])
    pattern_expressions = form_data.get("pattern_expression", [])
    pattern_actions = form_data.get("pattern_action", [])
    pattern_styles = form_data.get("pattern_style", [])

    # Ensure they are lists (in case there's only one item)
    if not isinstance(pattern_names, list):
        pattern_names = [pattern_names] if pattern_names else []
    if not isinstance(pattern_expressions, list):
        pattern_expressions = [pattern_expressions] if pattern_expressions else []
    if not isinstance(pattern_actions, list):
        pattern_actions = [pattern_actions] if pattern_actions else []
    if not isinstance(pattern_styles, list):
        pattern_styles = [pattern_styles] if pattern_styles else []

    # Pair them up by position
    max_length = max(
        len(pattern_names),
        len(pattern_expressions),
        len(pattern_actions),
        len(pattern_styles),
    )
    for i in range(max_length):
        name = (
            str(pattern_names[i]).strip()
            if i < len(pattern_names) and pattern_names[i]
            else ""
        )
        expression = (
            str(pattern_expressions[i]).strip()
            if i < len(pattern_expressions) and pattern_expressions[i]
            else ""
        )
        action = (
            str(pattern_actions[i]).strip()
            if i < len(pattern_actions) and pattern_actions[i]
            else "include"
        )
        style = (
            str(pattern_styles[i]).strip()
            if i < len(pattern_styles) and pattern_styles[i]
            else "sh"
        )

        # Only add patterns that have both name and expression
        if name and expression:
            patterns.append(
                {
                    "name": name,
                    "expression": expression,
                    "pattern_type": action,
                    "style": style,
                }
            )

    return json.dumps(patterns) if patterns else None


@router.get("/form", response_class=HTMLResponse)
async def get_schedules_form(
    request: Request,
    templates: TemplatesDep,
    config_service: ConfigurationServiceDep,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get schedules form with all dropdowns populated"""
    form_data = config_service.get_schedule_form_data()

    return templates.TemplateResponse(
        request,
        "partials/schedules/create_form.html",
        cast(Dict[str, Any], form_data),
    )


@router.post("/", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> HTMLResponse:
    try:
        json_data = await request.json()

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(json_data)
        )
        if not is_valid:
            return templates.TemplateResponse(
                request,
                "partials/schedules/create_error.html",
                {"error_message": error_msg},
            )

        schedule = ScheduleCreate(**processed_data)

    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": str(e)},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": f"Invalid form data: {str(e)}"},
        )

    result = await schedule_service.create_schedule(
        name=schedule.name,
        repository_id=schedule.repository_id,
        cron_expression=schedule.cron_expression,
        source_path=schedule.source_path or "",
        cloud_sync_config_id=schedule.cloud_sync_config_id,
        prune_config_id=schedule.prune_config_id,
        notification_config_id=schedule.notification_config_id,
        pre_job_hooks=schedule.pre_job_hooks,
        post_job_hooks=schedule.post_job_hooks,
        patterns=schedule.patterns,
    )

    if result.is_error or not result.schedule:
        return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": result.error_message},
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/create_success.html",
        {"schedule_name": result.schedule.name},
    )
    response.headers["HX-Trigger"] = "scheduleUpdate"
    return response


@router.get("/html", response_class=HTMLResponse)
def get_schedules_html(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    skip: int = 0,
    limit: int = 100,
) -> _TemplateResponse:
    """Get schedules as formatted HTML"""
    schedules = schedule_service.get_schedules(skip=skip, limit=limit)

    return templates.TemplateResponse(
        request,
        "partials/schedules/schedule_list_content.html",
        {"schedules": schedules},
    )


@router.get("/upcoming/html", response_class=HTMLResponse)
async def get_upcoming_backups_html(
    request: Request,
    templates: TemplatesDep,
    scheduler_service: SchedulerServiceDep,
    upcoming_backups_service: UpcomingBackupsServiceDep,
) -> HTMLResponse:
    """Get upcoming scheduled backups as formatted HTML"""
    try:
        jobs_raw = await scheduler_service.get_scheduled_jobs()
        processed_jobs = upcoming_backups_service.process_jobs(
            cast(List[Dict[str, object]], jobs_raw)
        )

        return templates.TemplateResponse(
            request,
            "partials/schedules/upcoming_backups_content.html",
            {"jobs": processed_jobs},
        )

    except Exception as e:
        return HTMLResponse(
            templates.get_template("partials/jobs/error_state.html").render(
                message=f"Error loading upcoming backups: {str(e)}", padding="4"
            )
        )


@router.get("/cron-expression-form", response_class=HTMLResponse)
async def get_cron_expression_form(
    request: Request,
    templates: TemplatesDep,
    config_service: ConfigurationServiceDep,
    preset: str = "",
) -> HTMLResponse:
    """Get dynamic cron expression form elements based on preset selection"""
    context = config_service.get_cron_form_context(preset)

    return templates.TemplateResponse(
        request,
        "partials/schedules/cron_expression_form.html",
        cast(Dict[str, Any], context),
    )


@router.get("/", response_class=HTMLResponse)
def list_schedules(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    skip: int = 0,
    limit: int = 100,
) -> _TemplateResponse:
    schedules = schedule_service.get_schedules(skip=skip, limit=limit)
    return templates.TemplateResponse(
        request,
        "partials/schedules/schedule_list_content.html",
        {"schedules": schedules},
    )


@router.get("/{schedule_id}", response_class=HTMLResponse)
def get_schedule(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> _TemplateResponse:
    schedule = schedule_service.get_schedule_by_id(schedule_id)
    if schedule is None:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": "Schedule not found"},
        )

    return templates.TemplateResponse(
        request, "partials/schedules/schedule_detail.html", {"schedule": schedule}
    )


@router.get("/{schedule_id}/edit", response_class=HTMLResponse)
async def get_schedule_edit_form(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    config_service: ConfigurationServiceDep,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get edit form for a specific schedule"""
    try:
        schedule = schedule_service.get_schedule_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="Schedule not found")

        form_data = config_service.get_schedule_form_data()
        context = {**form_data, "schedule": schedule, "is_edit_mode": True}

        return templates.TemplateResponse(
            request, "partials/schedules/edit_form.html", context
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {str(e)}")


@router.put("/{schedule_id}", response_class=HTMLResponse)
async def update_schedule(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> HTMLResponse:
    """Update a schedule"""
    try:
        json_data = await request.json()

        # The hooks and patterns are already in JSON format from the frontend
        # Just use them directly if they exist and are not empty
        if json_data.get("pre_job_hooks") and json_data["pre_job_hooks"].strip():
            # Already in JSON format, keep as is
            pass
        else:
            json_data["pre_job_hooks"] = None

        if json_data.get("post_job_hooks") and json_data["post_job_hooks"].strip():
            # Already in JSON format, keep as is
            pass
        else:
            json_data["post_job_hooks"] = None

        if json_data.get("patterns") and json_data["patterns"].strip():
            # Already in JSON format, keep as is
            pass
        else:
            json_data["patterns"] = None

        schedule_update = ScheduleUpdate(**json_data)
        update_data = schedule_update.model_dump(exclude_unset=True)

    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "partials/schedules/update_error.html",
            {"error_message": str(e)},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/schedules/update_error.html",
            {"error_message": f"Invalid form data: {str(e)}"},
        )

    result = await schedule_service.update_schedule(schedule_id, update_data)

    if result.is_error or not result.schedule:
        return templates.TemplateResponse(
            request,
            "partials/schedules/update_error.html",
            {"error_message": result.error_message},
            status_code=404
            if result.error_message and "not found" in result.error_message
            else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/update_success.html",
        {"schedule_name": result.schedule.name},
    )
    response.headers["HX-Trigger"] = "scheduleUpdate"
    return response


@router.put("/{schedule_id}/toggle", response_class=HTMLResponse)
async def toggle_schedule(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> HTMLResponse:
    result = await schedule_service.toggle_schedule(schedule_id)

    if result.is_error:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": result.error_message},
            status_code=404
            if result.error_message and "not found" in result.error_message
            else 500,
        )

    schedules = schedule_service.get_all_schedules()
    return templates.TemplateResponse(
        request,
        "partials/schedules/schedule_list_content.html",
        {"schedules": schedules},
    )


@router.delete("/{schedule_id}", response_class=HTMLResponse)
async def delete_schedule(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> HTMLResponse:
    result = await schedule_service.delete_schedule(schedule_id)

    if not result.success:
        return templates.TemplateResponse(
            request,
            "partials/schedules/delete_error.html",
            {"error_message": result.error_message},
            status_code=404
            if result.error_message and "not found" in result.error_message
            else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/delete_success.html",
        {"schedule_name": result.schedule_name},
    )
    response.headers["HX-Trigger"] = "scheduleUpdate"
    return response


@router.post("/{schedule_id}/run", response_class=HTMLResponse)
async def run_schedule_manually(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
) -> HTMLResponse:
    """Run a schedule manually"""
    result = await schedule_service.run_schedule_manually(schedule_id)

    if result.is_error:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": result.error_message},
            status_code=404
            if result.error_message and "not found" in result.error_message
            else 500,
        )

    # Get the schedule name for the success message
    schedule = schedule_service.get_schedule_by_id(schedule_id)
    schedule_name = schedule.name if schedule else "Unknown"

    return templates.TemplateResponse(
        request,
        "partials/schedules/run_success.html",
        {
            "schedule_name": schedule_name,
            "job_id": result.job_details.get("job_id") if result.job_details else None,
        },
    )


@router.get("/jobs/active", response_class=HTMLResponse)
async def get_active_scheduled_jobs(
    request: Request,
    templates: TemplatesDep,
    scheduler_service: SchedulerServiceDep,
) -> HTMLResponse:
    """Get all active scheduled jobs"""
    jobs = await scheduler_service.get_scheduled_jobs()
    return templates.TemplateResponse(
        request, "partials/schedules/active_jobs.html", {"jobs": jobs}
    )


@router.get("/cron/describe", response_class=HTMLResponse)
async def describe_cron_expression(
    request: Request,
    templates: TemplatesDep,
    custom_cron_input: str = Query(""),
) -> HTMLResponse:
    """Get human-readable description of a cron expression via HTMX."""
    cron_expression = custom_cron_input.strip()

    result = CronDescriptionService.get_human_description(cron_expression)

    return templates.TemplateResponse(
        request,
        "partials/schedules/cron_description.html",
        result,
    )


def _extract_hooks_from_form(form_data: Any, hook_type: str) -> List[Dict[str, Any]]:
    """Extract hooks from form data and return as list of dicts."""
    hooks = []

    # Get all names and commands for this hook type
    hook_names = form_data.getlist(f"{hook_type}_hook_name")
    hook_commands = form_data.getlist(f"{hook_type}_hook_command")
    hook_critical = form_data.getlist(f"{hook_type}_hook_critical")
    hook_run_on_failure = form_data.getlist(f"{hook_type}_hook_run_on_failure")

    # Pair them up by position
    for i in range(min(len(hook_names), len(hook_commands))):
        name = str(hook_names[i]).strip() if hook_names[i] else ""
        command = str(hook_commands[i]).strip() if hook_commands[i] else ""

        # Handle checkboxes - they're only present if checked
        critical = len(hook_critical) > i and hook_critical[i] == "true"
        run_on_failure = (
            len(hook_run_on_failure) > i and hook_run_on_failure[i] == "true"
        )

        # Add all hooks, even if name or command is empty (for reordering)
        hooks.append(
            {
                "name": name,
                "command": command,
                "critical": critical,
                "run_on_job_failure": run_on_failure,
            }
        )

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


@router.post("/hooks/add-hook-field", response_class=HTMLResponse)
async def add_hook_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Add a new hook field row via HTMX."""

    # Get form data (includes both hx-vals and hx-include data)
    form_data = await request.form()

    # Get hook_type from form data (sent via hx-vals)
    hook_type = str(form_data.get("hook_type", "pre"))

    current_hooks = _extract_hooks_from_form(form_data, hook_type)

    # Add a new empty hook
    current_hooks.append({"name": "", "command": ""})

    # Return updated container with all hooks (including the new one)
    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks/hooks_container.html",
        {"hook_type": hook_type, "hooks": current_hooks},
    )


@router.post("/hooks/move-hook", response_class=HTMLResponse)
async def move_hook(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Move a hook up or down in the list and return updated container."""
    form_data = await request.form()

    try:
        hook_type = str(form_data.get("hook_type", "pre"))
        index = int(str(form_data.get("index", "0")))
        direction = str(form_data.get("direction", "up"))  # "up" or "down"

        current_hooks = _extract_hooks_from_form(form_data, hook_type)

        if direction == "up" and index > 0 and index < len(current_hooks):
            current_hooks[index], current_hooks[index - 1] = (
                current_hooks[index - 1],
                current_hooks[index],
            )
        elif direction == "down" and index >= 0 and index < len(current_hooks) - 1:
            current_hooks[index], current_hooks[index + 1] = (
                current_hooks[index + 1],
                current_hooks[index],
            )

        return templates.TemplateResponse(
            request,
            "partials/schedules/hooks/hooks_container.html",
            {"hook_type": hook_type, "hooks": current_hooks},
        )

    except (ValueError, TypeError, KeyError):
        return HTMLResponse(content='<div class="space-y-4"></div>')


@router.post("/hooks/remove-hook-field", response_class=HTMLResponse)
async def remove_hook_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Remove a hook field row via HTMX."""

    form_data = await request.form()

    hook_type = str(form_data.get("hook_type", "pre"))

    current_hooks = _extract_hooks_from_form(form_data, hook_type)

    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks/hooks_container.html",
        {"hook_type": hook_type, "hooks": current_hooks},
    )


@router.post("/hooks/hooks-modal", response_class=HTMLResponse)
async def get_hooks_modal(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Open hooks configuration modal with current hook data passed from parent."""

    try:
        json_data = await request.json()

        # Get data from the actual form field names
        pre_hooks_json = str(json_data.get("pre_job_hooks", "[]"))
        post_hooks_json = str(json_data.get("post_job_hooks", "[]"))
    except (ValueError, TypeError, KeyError):
        pre_hooks_json = "[]"
        post_hooks_json = "[]"

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
    except (json.JSONDecodeError, TypeError):
        pre_hooks = []
        post_hooks = []

    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks/hooks_modal.html",
        {
            "pre_hooks": pre_hooks,
            "post_hooks": post_hooks,
            "pre_hooks_json": pre_hooks_json,
            "post_hooks_json": post_hooks_json,
        },
    )


@router.post("/hooks/save-hooks", response_class=HTMLResponse)
async def save_hooks(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Save hooks configuration and update parent component via OOB swap."""
    form_data = await request.form()

    is_valid, error_message = _validate_hooks_for_save(form_data)
    if not is_valid:
        return templates.TemplateResponse(
            request,
            "partials/schedules/hooks/hooks_validation_error.html",
            {"error_message": error_message},
            status_code=400,
        )

    pre_hooks_json = _convert_hook_fields_to_json(form_data, "pre")
    post_hooks_json = _convert_hook_fields_to_json(form_data, "post")

    try:
        pre_count = len(json.loads(pre_hooks_json)) if pre_hooks_json else 0
        post_count = len(json.loads(post_hooks_json)) if post_hooks_json else 0
    except (json.JSONDecodeError, TypeError):
        pre_count = 0
        post_count = 0

    total_count = pre_count + post_count

    return templates.TemplateResponse(
        request,
        "partials/schedules/hooks/hooks_save_response.html",
        {
            "pre_hooks_json": pre_hooks_json,
            "post_hooks_json": post_hooks_json,
            "total_count": total_count,
        },
    )


@router.get("/hooks/close-modal", response_class=HTMLResponse)
async def close_modal() -> HTMLResponse:
    """Close modal without saving."""
    return HTMLResponse(content='<div id="modal-container"></div>', status_code=200)


# Pattern-related helper functions
def _extract_patterns_from_form(form_data: Any) -> List[BackupPattern]:
    """Extract patterns from form data and return as list of BackupPattern objects."""
    patterns = []

    # Get all pattern data (new compact structure)
    pattern_names = form_data.getlist("pattern_name")
    pattern_expressions = form_data.getlist("pattern_expression")
    pattern_actions = form_data.getlist("pattern_action")
    pattern_styles = form_data.getlist("pattern_style")

    # Pair them up by position
    for i in range(
        min(len(pattern_names), len(pattern_expressions), len(pattern_actions))
    ):
        name = str(pattern_names[i]).strip() if pattern_names[i] else ""
        expression = (
            str(pattern_expressions[i]).strip() if pattern_expressions[i] else ""
        )
        action_str = (
            str(pattern_actions[i]).strip() if pattern_actions[i] else "include"
        )
        style_str = (
            str(pattern_styles[i]).strip()
            if len(pattern_styles) > i and pattern_styles[i]
            else "sh"
        )

        # Map action string to PatternType
        if action_str == "exclude":
            pattern_type = PatternType.EXCLUDE
        elif action_str == "exclude_norec":
            pattern_type = PatternType.EXCLUDE_NOREC
        else:
            pattern_type = PatternType.INCLUDE

        # Map style string to PatternStyle
        style_map = {
            "sh": PatternStyle.SHELL,
            "fm": PatternStyle.FNMATCH,
            "re": PatternStyle.REGEX,
            "pp": PatternStyle.PATH_PREFIX,
            "pf": PatternStyle.PATH_FULL,
        }
        pattern_style = style_map.get(style_str, PatternStyle.SHELL)

        # Add all patterns, even if name or expression is empty (for reordering)
        patterns.append(
            BackupPattern(
                name=name,
                expression=expression,
                pattern_type=pattern_type,
                style=pattern_style,
            )
        )

    return patterns


def _convert_patterns_to_json(form_data: Any) -> str | None:
    """Convert patterns to JSON format using unified structure."""
    patterns = _extract_patterns_from_form(form_data)

    # Filter out patterns that don't have both name and expression for JSON output
    valid_patterns = [
        {
            "name": pattern.name,
            "expression": pattern.expression,
            "pattern_type": pattern.pattern_type.value,
            "style": pattern.style.value,
        }
        for pattern in patterns
        if pattern.name and pattern.expression
    ]

    return json.dumps(valid_patterns) if valid_patterns else None


def _validate_patterns_for_save(form_data: Any) -> tuple[bool, str | None]:
    """Validate that all patterns have both name and expression filled out."""
    errors = []

    patterns = _extract_patterns_from_form(form_data)
    for i, pattern in enumerate(patterns):
        if not pattern.name.strip() and not pattern.expression.strip():
            # Empty pattern - skip (will be filtered out)
            continue
        elif not pattern.name.strip():
            errors.append(f"Pattern #{i + 1}: Pattern name is required")
        elif not pattern.expression.strip():
            errors.append(f"Pattern #{i + 1}: Pattern expression is required")

    if errors:
        return False, "; ".join(errors)
    return True, None


# Pattern API endpoints
@router.post("/patterns/add-pattern-field", response_class=HTMLResponse)
async def add_pattern_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Add a new pattern field row via HTMX."""

    # Get form data (includes both hx-vals and hx-include data)
    form_data = await request.form()

    current_patterns = _extract_patterns_from_form(form_data)

    # Add a new empty pattern (default to include with shell style)
    current_patterns.append(
        BackupPattern(
            name="",
            expression="",
            pattern_type=PatternType.INCLUDE,
            style=PatternStyle.SHELL,
        )
    )

    # Return updated container with all patterns (including the new one)
    return templates.TemplateResponse(
        request,
        "partials/schedules/patterns/patterns_container.html",
        {"patterns": current_patterns},
    )


@router.post("/patterns/move-pattern", response_class=HTMLResponse)
async def move_pattern(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Move a pattern up or down in the list and return updated container."""
    form_data = await request.form()

    try:
        index = int(str(form_data.get("index", "0")))
        direction = str(form_data.get("direction", "up"))  # "up" or "down"

        current_patterns = _extract_patterns_from_form(form_data)

        if direction == "up" and index > 0 and index < len(current_patterns):
            current_patterns[index], current_patterns[index - 1] = (
                current_patterns[index - 1],
                current_patterns[index],
            )
        elif direction == "down" and index >= 0 and index < len(current_patterns) - 1:
            current_patterns[index], current_patterns[index + 1] = (
                current_patterns[index + 1],
                current_patterns[index],
            )

        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_container.html",
            {"patterns": current_patterns},
        )

    except (ValueError, TypeError, KeyError):
        return HTMLResponse(content='<div class="space-y-4"></div>')


@router.post("/patterns/remove-pattern-field", response_class=HTMLResponse)
async def remove_pattern_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Remove a pattern field row via HTMX."""

    form_data = await request.form()

    try:
        index = int(str(form_data.get("index", "0")))

        current_patterns = _extract_patterns_from_form(form_data)

        # Remove the pattern at the specified index
        if 0 <= index < len(current_patterns):
            current_patterns.pop(index)

        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_container.html",
            {"patterns": current_patterns},
        )

    except (ValueError, TypeError, KeyError):
        return HTMLResponse(content='<div class="space-y-4"></div>')


@router.post("/patterns/patterns-modal", response_class=HTMLResponse)
async def get_patterns_modal(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Open patterns configuration modal with current pattern data passed from parent."""

    try:
        # Get JSON data from hx-include="#patterns_field"
        json_data = await request.json()
        patterns_json = str(json_data.get("patterns", "[]"))

    except Exception as e:
        print(f"DEBUG: Exception getting JSON data: {e}")
        patterns_json = "[]"

    try:
        patterns_data = (
            json.loads(patterns_json) if patterns_json and patterns_json != "[]" else []
        )

        # Convert to BackupPattern objects
        patterns = [
            BackupPattern(
                name=p.get("name", ""),
                expression=p.get("expression", ""),
                pattern_type=PatternType(p.get("pattern_type", "include")),
                style=PatternStyle(p.get("style", "sh")),
            )
            for p in patterns_data
        ]

    except (json.JSONDecodeError, TypeError):
        patterns = []

    return templates.TemplateResponse(
        request,
        "partials/schedules/patterns/patterns_modal.html",
        {
            "patterns": patterns,
            "patterns_json": patterns_json,
        },
    )


@router.post("/patterns/save-patterns", response_class=HTMLResponse)
async def save_patterns(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Save patterns configuration and update parent component via OOB swap."""
    form_data = await request.form()

    is_valid, error_message = _validate_patterns_for_save(form_data)
    if not is_valid:
        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_validation_error.html",
            {"error_message": error_message},
            status_code=400,
        )

    patterns_json = _convert_patterns_to_json(form_data)

    try:
        total_count = len(json.loads(patterns_json)) if patterns_json else 0
    except (json.JSONDecodeError, TypeError):
        total_count = 0

    return templates.TemplateResponse(
        request,
        "partials/schedules/patterns/patterns_save_response.html",
        {
            "patterns_json": patterns_json,
            "total_count": total_count,
        },
    )


@router.post("/patterns/validate-all-patterns", response_class=HTMLResponse)
async def validate_all_patterns_endpoint(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Validate all patterns and return validation results."""
    try:
        form_data = await request.form()

        # Extract all patterns from form data
        patterns = _extract_patterns_from_form(form_data)

        # Validate each pattern
        validation_results = []

        for i, pattern in enumerate(patterns):
            # Skip empty patterns
            if not pattern.name.strip() and not pattern.expression.strip():
                continue

            # Check for required fields
            if not pattern.expression.strip():
                validation_results.append(
                    {
                        "index": i,
                        "name": pattern.name or f"Pattern #{i + 1}",
                        "is_valid": False,
                        "error": "Pattern expression is required",
                        "warnings": [],
                    }
                )
                continue

            # Map action to validation format
            action_map = {
                PatternType.INCLUDE: "+",
                PatternType.EXCLUDE: "-",
                PatternType.EXCLUDE_NOREC: "!",
            }
            action = action_map.get(pattern.pattern_type, "+")

            # Validate the pattern
            is_valid, error, warnings = validate_pattern(
                pattern_str=pattern.expression, style=pattern.style.value, action=action
            )

            validation_results.append(
                {
                    "index": i,
                    "name": pattern.name or f"Pattern #{i + 1}",
                    "is_valid": is_valid,
                    "error": error,
                    "warnings": warnings,
                }
            )

        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_validation_results.html",
            {
                "validation_results": validation_results,
                "total_patterns": len(validation_results),
                "valid_patterns": sum(1 for r in validation_results if r["is_valid"]),
            },
        )

    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_validation_results.html",
            {
                "validation_results": [
                    {
                        "index": 0,
                        "name": "Validation Error",
                        "is_valid": False,
                        "error": f"Validation error: {str(e)}",
                        "warnings": [],
                    }
                ],
                "total_patterns": 1,
                "valid_patterns": 0,
            },
        )


@router.get("/patterns/close-modal", response_class=HTMLResponse)
async def close_patterns_modal() -> HTMLResponse:
    """Close patterns modal without saving."""
    return HTMLResponse(content='<div id="modal-container"></div>', status_code=200)
