from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

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
    templates: TemplatesDep,
    scheduler_service: SchedulerServiceDep,
    upcoming_backups_service: UpcomingBackupsServiceDep,
):
    """Get upcoming scheduled backups as formatted HTML"""
    try:
        jobs_raw = await scheduler_service.get_scheduled_jobs()
        processed_jobs = upcoming_backups_service.process_jobs(jobs_raw)

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


@router.get("/cron/describe", response_class=HTMLResponse)
async def describe_cron_expression(
    request: Request,
    templates: TemplatesDep,
    custom_cron_input: str = Query(""),
):
    """Get human-readable description of a cron expression via HTMX."""
    cron_expression = custom_cron_input.strip()

    result = CronDescriptionService.get_human_description(cron_expression)

    return templates.TemplateResponse(
        request,
        "partials/schedules/cron_description.html",
        result,
    )
