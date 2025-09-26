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

        # Convert hook fields to JSON format
        pre_hooks_json = convert_hook_fields_to_json(json_data, "pre")
        post_hooks_json = convert_hook_fields_to_json(json_data, "post")

        # Add converted hooks to json_data
        if pre_hooks_json:
            json_data["pre_job_hooks"] = pre_hooks_json
        if post_hooks_json:
            json_data["post_job_hooks"] = post_hooks_json

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

    success, created_schedule, error_msg = await schedule_service.create_schedule(
        name=schedule.name,
        repository_id=schedule.repository_id,
        cron_expression=schedule.cron_expression,
        source_path=schedule.source_path or "",
        cloud_sync_config_id=schedule.cloud_sync_config_id,
        prune_config_id=schedule.prune_config_id,
        notification_config_id=schedule.notification_config_id,
        pre_job_hooks=schedule.pre_job_hooks,
        post_job_hooks=schedule.post_job_hooks,
    )

    if not success or not created_schedule:
        return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": error_msg},
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/create_success.html",
        {"schedule_name": created_schedule.name},
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

        return HTMLResponse(
            templates.get_template(
                "partials/schedules/upcoming_backups_content.html"
            ).render(jobs=processed_jobs)
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

        # Convert hook fields to JSON format
        pre_hooks_json = convert_hook_fields_to_json(json_data, "pre")
        post_hooks_json = convert_hook_fields_to_json(json_data, "post")

        # Add converted hooks to json_data
        if pre_hooks_json:
            json_data["pre_job_hooks"] = pre_hooks_json
        if post_hooks_json:
            json_data["post_job_hooks"] = post_hooks_json

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

    success, updated_schedule, error_msg = await schedule_service.update_schedule(
        schedule_id, update_data
    )

    if not success or not updated_schedule:
        return templates.TemplateResponse(
            request,
            "partials/schedules/update_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/update_success.html",
        {"schedule_name": updated_schedule.name},
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
    success, updated_schedule, error_msg = await schedule_service.toggle_schedule(
        schedule_id
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
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
    success, schedule_name, error_msg = await schedule_service.delete_schedule(
        schedule_id
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/schedules/delete_error.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    response = templates.TemplateResponse(
        request,
        "partials/schedules/delete_success.html",
        {"schedule_name": schedule_name},
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
    success, job_id, error_msg = await schedule_service.run_schedule_manually(
        schedule_id
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": error_msg},
            status_code=404 if error_msg and "not found" in error_msg else 500,
        )

    # Get the schedule name for the success message
    schedule = schedule_service.get_schedule_by_id(schedule_id)
    schedule_name = schedule.name if schedule else "Unknown"

    return templates.TemplateResponse(
        request,
        "partials/schedules/run_success.html",
        {"schedule_name": schedule_name, "job_id": job_id},
    )


@router.get("/jobs/active", response_class=HTMLResponse)
async def get_active_scheduled_jobs(
    templates: TemplatesDep,
    scheduler_service: SchedulerServiceDep,
) -> HTMLResponse:
    """Get all active scheduled jobs"""
    jobs = await scheduler_service.get_scheduled_jobs()
    return HTMLResponse(
        templates.get_template("partials/schedules/active_jobs.html").render(jobs=jobs)
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

        pre_hooks_json = str(json_data.get("pre_hooks", "[]"))
        post_hooks_json = str(json_data.get("post_hooks", "[]"))
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
