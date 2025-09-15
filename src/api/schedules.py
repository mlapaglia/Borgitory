from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from models.database import get_db
from models.schemas import (
    ScheduleCreate,
    ScheduleUpdate,
)
from dependencies import (
    SchedulerServiceDep,
    TemplatesDep,
    ScheduleServiceDep,
    ConfigurationServiceDep,
)
from services.cron_description_service import CronDescriptionService

router = APIRouter()


@router.get("/form", response_class=HTMLResponse)
async def get_schedules_form(
    request: Request,
    templates: TemplatesDep,
    config_service: ConfigurationServiceDep,
    db: Session = Depends(get_db),
):
    """Get schedules form with all dropdowns populated"""
    form_data = config_service.get_schedule_form_data(db)

    return templates.TemplateResponse(
        request,
        "partials/schedules/create_form.html",
        form_data,
    )


@router.post("/", response_class=HTMLResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
):
    try:
        json_data = await request.json()
        
        # Validate and process data using service
        is_valid, processed_data, error_msg = schedule_service.validate_schedule_creation_data(json_data)
        if not is_valid:
            return templates.TemplateResponse(
                request,
                "partials/schedules/create_error.html",
                {"error_message": error_msg},
            )
        
        # Create Pydantic model for additional validation
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
        source_path=schedule.source_path,
        cloud_sync_config_id=schedule.cloud_sync_config_id,
        cleanup_config_id=schedule.cleanup_config_id,
        notification_config_id=schedule.notification_config_id,
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": error_msg},
        )

    # Success response
    response = templates.TemplateResponse(
        request,
        "partials/schedules/create_success.html",
        {"schedule_name": created_schedule.name},
    )
    response.headers["HX-Trigger"] = "scheduleUpdate"
    return response


@router.get("/html", response_class=HTMLResponse)
def get_schedules_html(
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    skip: int = 0,
    limit: int = 100,
):
    """Get schedules as formatted HTML"""
    schedules = schedule_service.get_schedules(skip=skip, limit=limit)

    return templates.get_template(
        "partials/schedules/schedule_list_content.html"
    ).render(schedules=schedules)


@router.get("/upcoming/html", response_class=HTMLResponse)
async def get_upcoming_backups_html(
    templates: TemplatesDep, scheduler_service: SchedulerServiceDep
):
    """Get upcoming scheduled backups as formatted HTML"""
    try:
        jobs_raw = await scheduler_service.get_scheduled_jobs()

        # Process jobs to add computed fields for template
        processed_jobs = []
        for job in jobs_raw:
            try:
                # Handle different datetime formats from APScheduler
                next_run_raw = job.get("next_run")
                if not next_run_raw:
                    continue

                # Convert to datetime object if it's not already
                if isinstance(next_run_raw, str):
                    # Try different datetime formats
                    try:
                        next_run = datetime.fromisoformat(
                            next_run_raw.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        try:
                            next_run = datetime.fromisoformat(next_run_raw)
                        except (ValueError, TypeError):
                            # Skip if we can't parse the datetime
                            continue
                else:
                    # Assume it's already a datetime object
                    next_run = next_run_raw

                # Calculate time difference
                now = datetime.now()
                if next_run.tzinfo:
                    # If next_run is timezone aware, make now timezone aware too
                    now = datetime.now(timezone.utc)

                time_diff_seconds = (next_run - now).total_seconds()
                time_diff_ms = int(time_diff_seconds * 1000)
                time_until = format_time_until(time_diff_ms)

                # Format cron description
                cron_description = format_cron_trigger(job.get("trigger", ""))

                # Format the datetime for display
                next_run_display = next_run.strftime("%m/%d/%Y, %I:%M:%S %p")

                # Create processed job object for template
                processed_job = {
                    "name": job.get("name", "Unknown"),
                    "next_run_display": next_run_display,
                    "time_until": time_until,
                    "cron_description": cron_description,
                }
                processed_jobs.append(processed_job)

            except Exception as job_error:
                # Skip individual jobs that fail to process
                print(f"Error processing job {job.get('name', 'Unknown')}: {job_error}")
                continue

        return templates.get_template(
            "partials/schedules/upcoming_backups_content.html"
        ).render(jobs=processed_jobs)

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading upcoming backups: {str(e)}", padding="4"
        )


@router.get("/cron-expression-form", response_class=HTMLResponse)
async def get_cron_expression_form(
    request: Request,
    templates: TemplatesDep,
    config_service: ConfigurationServiceDep,
    preset: str = "",
):
    """Get dynamic cron expression form elements based on preset selection"""
    context = config_service.get_cron_form_context(preset)

    return templates.TemplateResponse(
        request, "partials/schedules/cron_expression_form.html", context
    )


@router.get("/", response_class=HTMLResponse)
def list_schedules(
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
    skip: int = 0,
    limit: int = 100,
):
    schedules = schedule_service.get_schedules(skip=skip, limit=limit)
    return templates.get_template(
        "partials/schedules/schedule_list_content.html"
    ).render(schedules=schedules)


@router.get("/{schedule_id}", response_class=HTMLResponse)
def get_schedule(
    schedule_id: int,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
):
    schedule = schedule_service.get_schedule_by_id(schedule_id)
    if schedule is None:
        return templates.get_template("partials/common/error_message.html").render(
            error_message="Schedule not found"
        )
    return templates.get_template("partials/schedules/schedule_detail.html").render(
        schedule=schedule
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

        # Get all the dropdown options
        form_data = config_service.get_schedule_form_data(db)
        form_data["schedule"] = schedule
        form_data["is_edit_mode"] = True

        return templates.TemplateResponse(
            request, "partials/schedules/edit_form.html", form_data
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {str(e)}")


@router.put("/{schedule_id}", response_class=HTMLResponse)
async def update_schedule(
    schedule_id: int,
    schedule_update: ScheduleUpdate,
    request: Request,
    templates: TemplatesDep,
    schedule_service: ScheduleServiceDep,
):
    """Update a schedule"""
    update_data = schedule_update.model_dump(exclude_unset=True)
    success, updated_schedule, error_msg = await schedule_service.update_schedule(
        schedule_id, update_data
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/schedules/update_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
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
):
    success, updated_schedule, error_msg = await schedule_service.toggle_schedule(
        schedule_id
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/common/error_message.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    # Return updated schedule list
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
):
    success, schedule_name, error_msg = await schedule_service.delete_schedule(
        schedule_id
    )

    if not success:
        return templates.TemplateResponse(
            request,
            "partials/schedules/delete_error.html",
            {"error_message": error_msg},
            status_code=404 if "not found" in error_msg else 500,
        )

    # Success response
    response = templates.TemplateResponse(
        request,
        "partials/schedules/delete_success.html",
        {"schedule_name": schedule_name},
    )
    response.headers["HX-Trigger"] = "scheduleUpdate"
    return response


@router.get("/jobs/active", response_class=HTMLResponse)
async def get_active_scheduled_jobs(
    templates: TemplatesDep,
    scheduler_service: SchedulerServiceDep,
):
    """Get all active scheduled jobs"""
    jobs = await scheduler_service.get_scheduled_jobs()
    return templates.get_template("partials/schedules/active_jobs.html").render(
        jobs=jobs
    )


def format_cron_trigger(trigger_str: str) -> str:
    """Convert cron trigger to human readable format"""
    try:
        import re

        cron_match = re.search(r"cron\[([^\]]+)\]", trigger_str)
        if not cron_match:
            return trigger_str

        cron_parts = {}
        parts = cron_match.group(1).split(", ")

        for part in parts:
            key, value = part.split("=", 1)
            cron_parts[key] = value.strip("'")

        minute = cron_parts.get("minute", "*")
        hour = cron_parts.get("hour", "*")
        day = cron_parts.get("day", "*")
        month = cron_parts.get("month", "*")
        day_of_week = cron_parts.get("day_of_week", "*")

        # Convert to human readable format
        if (
            minute == "0"
            and hour != "*"
            and day == "*"
            and month == "*"
            and day_of_week == "*"
        ):
            return f"Daily at {format_hour(hour)}"
        elif (
            minute == "0"
            and hour != "*"
            and day == "*"
            and month == "*"
            and day_of_week != "*"
        ):
            day_name = get_day_name(day_of_week)
            return f"Weekly on {day_name} at {format_hour(hour)}"
        elif (
            minute == "0"
            and hour != "*"
            and day != "*"
            and month == "*"
            and day_of_week == "*"
        ):
            if "," in day:
                return f"Twice monthly ({day}) at {format_hour(hour)}"
            elif "/" in day:
                return f"Every {day.split('/')[1]} days at {format_hour(hour)}"
            else:
                return f"Monthly on {day} at {format_hour(hour)}"
        elif minute == "0" and hour != "*" and "-" in day and day_of_week != "*":
            day_name = get_day_name(day_of_week)
            return f"Third {day_name} of month at {format_hour(hour)}"
        else:
            return f"{minute} {hour} {day} {month} {day_of_week}"
    except (ValueError, KeyError, AttributeError):
        return trigger_str


def format_hour(hour_str: str) -> str:
    """Convert 24-hour to 12-hour format"""
    try:
        h = int(hour_str)
        if h == 0:
            return "12:00 AM"
        elif h < 12:
            return f"{h}:00 AM"
        elif h == 12:
            return "12:00 PM"
        else:
            return f"{h - 12}:00 PM"
    except (ValueError, TypeError):
        return hour_str


def get_day_name(day_of_week: str) -> str:
    """Convert day number to day name"""
    days = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]
    try:
        return days[int(day_of_week)]
    except (ValueError, IndexError, TypeError):
        return "Unknown"


def format_time_until(milliseconds: int) -> str:
    """Format time until next run"""
    if milliseconds < 0:
        return "Overdue"

    seconds = milliseconds // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h"
    elif hours > 0:
        remaining_minutes = minutes % 60
        return f"{hours}h {remaining_minutes}m"
    elif minutes > 0:
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{seconds}s"


@router.get("/cron/describe", response_class=HTMLResponse)
async def describe_cron_expression(
    request: Request,
    templates: TemplatesDep,
    custom_cron_input: str = "",
):
    """Get human-readable description of a cron expression via HTMX."""
    cron_expression = custom_cron_input.strip()
    
    result = CronDescriptionService.get_human_description(cron_expression)
    
    return templates.TemplateResponse(
        request,
        "partials/schedules/cron_description.html",
        result,
    )
