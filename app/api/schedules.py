from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import Schedule, Repository, get_db
from app.models.schemas import Schedule as ScheduleSchema, ScheduleCreate
from app.services.scheduler_service import scheduler_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/form")
async def get_schedules_form(request: Request, db: Session = Depends(get_db)):
    """Get schedules form with all dropdowns populated"""
    from app.models.database import (
        CleanupConfig,
        CloudSyncConfig,
        NotificationConfig,
        RepositoryCheckConfig,
    )

    repositories = db.query(Repository).all()
    cleanup_configs = db.query(CleanupConfig).filter(CleanupConfig.enabled).all()
    cloud_sync_configs = db.query(CloudSyncConfig).filter(CloudSyncConfig.enabled).all()
    notification_configs = (
        db.query(NotificationConfig).filter(NotificationConfig.enabled).all()
    )
    check_configs = (
        db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.enabled).all()
    )

    return templates.TemplateResponse(
        request,
        "partials/schedules/create_form.html",
        {
            "repositories": repositories,
            "cleanup_configs": cleanup_configs,
            "cloud_sync_configs": cloud_sync_configs,
            "notification_configs": notification_configs,
            "check_configs": check_configs,
        },
    )


@router.post("/", response_model=ScheduleSchema, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: Request, schedule: ScheduleCreate, db: Session = Depends(get_db)
):
    is_htmx_request = "hx-request" in request.headers

    try:
        repository = (
            db.query(Repository).filter(Repository.id == schedule.repository_id).first()
        )
        if not repository:
            error_msg = "Repository not found"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/schedules/create_error.html",
                    {"error_message": error_msg},
                    status_code=404,
                )
            raise HTTPException(status_code=404, detail=error_msg)

        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(schedule.cron_expression)
        except ValueError as e:
            error_msg = f"Invalid cron expression: {str(e)}"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/schedules/create_error.html",
                    {"error_message": error_msg},
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        db_schedule = Schedule(
            name=schedule.name,
            repository_id=schedule.repository_id,
            cron_expression=schedule.cron_expression,
            source_path=schedule.source_path,
            enabled=True,
            cloud_sync_config_id=schedule.cloud_sync_config_id,
            cleanup_config_id=schedule.cleanup_config_id,
            notification_config_id=schedule.notification_config_id,
        )

        db.add(db_schedule)
        db.commit()
        db.refresh(db_schedule)

        # Add to scheduler
        try:
            await scheduler_service.add_schedule(
                db_schedule.id, db_schedule.name, db_schedule.cron_expression
            )
        except Exception as e:
            # Rollback database changes if scheduler fails
            db.delete(db_schedule)
            db.commit()
            error_msg = f"Failed to schedule job: {str(e)}"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/schedules/create_error.html",
                    {"error_message": error_msg},
                    status_code=500,
                )
            raise HTTPException(status_code=500, detail=error_msg)

        # Success response
        if is_htmx_request:
            # Trigger schedule list update and return success message
            response = templates.TemplateResponse(
                request,
                "partials/schedules/create_success.html",
                {"schedule_name": schedule.name},
            )
            response.headers["HX-Trigger"] = "scheduleUpdate"
            return response
        else:
            # Return JSON for non-HTMX requests
            return db_schedule

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": str(e.detail)},
            status_code=e.status_code,
        )
        raise
    except Exception as e:
        db.rollback()
        error_msg = f"Failed to create schedule: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
            request,
            "partials/schedules/create_error.html",
            {"error_message": error_msg},
            status_code=500,
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/html", response_class=HTMLResponse)
def get_schedules_html(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Get schedules as formatted HTML"""
    schedules = db.query(Schedule).offset(skip).limit(limit).all()

    return templates.get_template(
        "partials/schedules/schedule_list_content.html"
    ).render(schedules=schedules)


@router.get("/upcoming/html", response_class=HTMLResponse)
async def get_upcoming_backups_html():
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
                    from datetime import timezone

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


@router.get("/cron-expression-form")
async def get_cron_expression_form(request: Request, preset: str = ""):
    """Get dynamic cron expression form elements based on preset selection"""
    context = {
        "preset": preset,
        "is_custom": preset == "custom",
        "cron_expression": preset if preset != "custom" and preset else "",
        "description": "",
    }

    # Get human readable description for preset
    if preset and preset != "custom":
        preset_descriptions = {
            "0 2 * * *": "Daily at 2:00 AM",
            "0 2 * * 0": "Weekly on Sunday at 2:00 AM",
            "0 2 1 * *": "Monthly on 1st at 2:00 AM",
            "0 2 1,15 * *": "Twice monthly (1st and 15th) at 2:00 AM",
            "0 2 */2 * *": "Every 2 days at 2:00 AM",
        }
        context["description"] = preset_descriptions.get(preset, "")

    return templates.TemplateResponse(
        "partials/schedules/cron_expression_form.html", context
    )


@router.post("/cron-expression-form")
async def update_cron_expression_form(request: Request):
    """Update cron expression form with custom input"""
    form_data = await request.form()
    preset = request.query_params.get("preset", "")
    custom_input = form_data.get("custom_cron_input", "").strip()

    context = {
        "preset": preset,
        "is_custom": preset == "custom",
        "cron_expression": custom_input if preset == "custom" else preset,
        "description": "",
    }

    return templates.TemplateResponse(
        "partials/schedules/cron_expression_form.html", context
    )


@router.get("/", response_model=List[ScheduleSchema])
def list_schedules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    schedules = db.query(Schedule).offset(skip).limit(limit).all()
    return schedules


@router.get("/{schedule_id}", response_model=ScheduleSchema)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.put("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.enabled = not schedule.enabled
    db.commit()

    # Update scheduler
    try:
        await scheduler_service.update_schedule(
            schedule.id, schedule.name, schedule.cron_expression, schedule.enabled
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update schedule: {str(e)}"
        )

    return {"message": f"Schedule {'enabled' if schedule.enabled else 'disabled'}"}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Remove from scheduler
    await scheduler_service.remove_schedule(schedule_id)

    # Delete from database
    db.delete(schedule)
    db.commit()

    return {"message": "Schedule deleted successfully"}


@router.get("/jobs/active")
async def get_active_scheduled_jobs():
    """Get all active scheduled jobs"""
    return {"jobs": await scheduler_service.get_scheduled_jobs()}


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
