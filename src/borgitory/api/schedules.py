from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import _TemplateResponse
from typing import cast, List, Dict, Any, Optional
import json

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
    get_db,
)
from borgitory.services.cron_description_service import CronDescriptionService
from borgitory.models.patterns import BackupPattern, PatternType, PatternStyle
from borgitory.services.scheduling.pattern_service import PatternService
from borgitory.services.scheduling.hook_service import HookService

router = APIRouter()


def convert_hook_fields_to_json(
    form_data: Dict[str, Any], hook_type: str
) -> Optional[str]:
    """Convert individual hook fields to JSON format using position-based form data."""
    return HookService.convert_hook_fields_to_json_from_dict(form_data, hook_type)


@router.get("/form", response_class=HTMLResponse)
async def get_schedules_form(
    request: Request,
    templates: TemplatesDep,
    config_service: ConfigurationServiceDep,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get schedules form with all dropdowns populated"""
    form_data = await config_service.get_schedule_form_data(db)

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
    db: AsyncSession = Depends(get_db),
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
        db,
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
async def get_schedules_html(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> _TemplateResponse:
    """Get schedules as formatted HTML"""
    schedules = await schedule_service.get_schedules(db, skip=skip, limit=limit)

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
async def list_schedules(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> _TemplateResponse:
    schedules = await schedule_service.get_schedules(db, skip=skip, limit=limit)
    return templates.TemplateResponse(
        request,
        "partials/schedules/schedule_list_content.html",
        {"schedules": schedules},
    )


@router.get("/{schedule_id}", response_class=HTMLResponse)
async def get_schedule(
    schedule_id: int,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    db: AsyncSession = Depends(get_db),
) -> _TemplateResponse:
    schedule = await schedule_service.get_schedule_by_id(schedule_id, db)
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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get edit form for a specific schedule"""
    try:
        schedule = await schedule_service.get_schedule_by_id(schedule_id, db)
        if schedule is None:
            raise HTTPException(status_code=404, detail="Schedule not found")

        form_data = await config_service.get_schedule_form_data(db)
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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Update a schedule"""
    try:
        json_data = await request.json()

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

    result = await schedule_service.update_schedule(schedule_id, db, update_data)

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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    result = await schedule_service.toggle_schedule(schedule_id, db)

    if result.is_error:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": result.error_message},
            status_code=404
            if result.error_message and "not found" in result.error_message
            else 500,
        )

    schedules = await schedule_service.get_all_schedules(db)
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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    result = await schedule_service.delete_schedule(schedule_id, db)

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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Run a schedule manually"""
    result = await schedule_service.run_schedule_manually(schedule_id, db)

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
    schedule = await schedule_service.get_schedule_by_id(schedule_id, db)
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

    current_hooks = HookService.extract_hooks_from_form(form_data, hook_type)

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

        current_hooks = HookService.extract_hooks_from_form(form_data, hook_type)

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

    try:
        hook_type = str(form_data.get("hook_type", "pre"))
        index = int(str(form_data.get("index", "0")))

        current_hooks = HookService.extract_hooks_from_form(form_data, hook_type)

        # Remove the hook at the specified index
        if 0 <= index < len(current_hooks):
            current_hooks.pop(index)

        return templates.TemplateResponse(
            request,
            "partials/schedules/hooks/hooks_container.html",
            {"hook_type": hook_type, "hooks": current_hooks},
        )

    except (ValueError, TypeError, KeyError):
        return HTMLResponse(content='<div class="space-y-4"></div>')


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

    pre_hooks = HookService.parse_hooks_from_json(pre_hooks_json)
    post_hooks = HookService.parse_hooks_from_json(post_hooks_json)

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

    is_valid, error_message = HookService.validate_hooks_for_save(form_data)
    if not is_valid:
        return templates.TemplateResponse(
            request,
            "partials/schedules/hooks/hooks_validation_error.html",
            {"error_message": error_message},
            status_code=400,
        )

    pre_hooks_json = HookService.convert_hook_fields_to_json(form_data, "pre")
    post_hooks_json = HookService.convert_hook_fields_to_json(form_data, "post")

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


# Pattern API endpoints
@router.post("/patterns/add-pattern-field", response_class=HTMLResponse)
async def add_pattern_field(
    request: Request,
    templates: TemplatesDep,
) -> HTMLResponse:
    """Add a new pattern field row via HTMX."""

    form_data = await request.form()

    current_patterns = PatternService.extract_patterns_from_form(form_data)

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
        direction = str(form_data.get("direction", "up"))

        current_patterns = PatternService.extract_patterns_from_form(form_data)

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

        current_patterns = PatternService.extract_patterns_from_form(form_data)

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
        json_data = await request.json()
        patterns_json = str(json_data.get("patterns", "[]"))

    except Exception:
        patterns_json = "[]"

    patterns = PatternService.parse_patterns_from_json(patterns_json)

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

    is_valid, error_message = PatternService.validate_patterns_for_save(form_data)
    if not is_valid:
        return templates.TemplateResponse(
            request,
            "partials/schedules/patterns/patterns_validation_error.html",
            {"error_message": error_message},
            status_code=400,
        )

    patterns_json = PatternService.convert_patterns_to_json(form_data)

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

        patterns = PatternService.extract_patterns_from_form(form_data)

        validation_results = PatternService.validate_all_patterns(patterns)

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
