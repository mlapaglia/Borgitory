from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_db, RepositoryCheckConfig
from app.models.schemas import (
    RepositoryCheckConfigCreate,
    RepositoryCheckConfigUpdate,
    RepositoryCheckConfig as RepositoryCheckConfigSchema,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/", response_model=RepositoryCheckConfigSchema)
async def create_repository_check_config(
    request: Request, config: RepositoryCheckConfigCreate, db: Session = Depends(get_db)
):
    """Create a new repository check configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        # Check if name already exists
        existing = (
            db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.name == config.name)
            .first()
        )
        if existing:
            error_msg = "A check policy with this name already exists"
            if is_htmx_request:
                return templates.TemplateResponse(
                    "partials/repository_check/create_error.html",
                    {"request": request, "error_message": error_msg},
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail=error_msg)

        # Create the config
        db_config = RepositoryCheckConfig(
            name=config.name,
            description=config.description,
            check_type=config.check_type,
            verify_data=config.verify_data,
            repair_mode=config.repair_mode,
            save_space=config.save_space,
            max_duration=config.max_duration,
            archive_prefix=config.archive_prefix,
            archive_glob=config.archive_glob,
            first_n_archives=config.first_n_archives,
            last_n_archives=config.last_n_archives,
        )

        db.add(db_config)
        db.commit()
        db.refresh(db_config)

        if is_htmx_request:
            response = templates.TemplateResponse(
                "partials/repository_check/create_success.html",
                {"request": request, "config_name": config.name},
            )
            response.headers["HX-Trigger"] = "checkConfigUpdate"
            return response
        else:
            return db_config

    except Exception as e:
        error_msg = f"Failed to create check policy: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                "partials/repository_check/create_error.html",
                {"request": request, "error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[RepositoryCheckConfigSchema])
def get_repository_check_configs(db: Session = Depends(get_db)):
    """Get all repository check configurations"""
    return db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()


@router.get("/form")
async def get_repository_check_form(request: Request, db: Session = Depends(get_db)):
    """Get repository check form with all dropdowns populated"""
    from app.models.database import Repository

    repositories = db.query(Repository).all()
    check_configs = (
        db.query(RepositoryCheckConfig).filter(RepositoryCheckConfig.enabled).all()
    )

    return templates.TemplateResponse(
        "partials/repository_check/form.html",
        {
            "request": request,
            "repositories": repositories,
            "check_configs": check_configs,
        },
    )


@router.get("/html", response_class=HTMLResponse)
def get_repository_check_configs_html(request: Request, db: Session = Depends(get_db)):
    """Get repository check configurations as HTML"""
    try:
        configs = (
            db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()
        )
        return templates.TemplateResponse(
            "partials/repository_check/config_list_content.html",
            {"request": request, "configs": configs},
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/common/error_message.html",
            {
                "request": request,
                "error_message": f"Error loading check policies: {str(e)}",
            },
        )


@router.get("/toggle-custom-options", response_class=HTMLResponse)
def toggle_custom_options(request: Request, check_config_id: str = ""):
    """Toggle custom check options visibility based on policy selection"""

    # If a policy is selected (check_config_id has a value), hide custom options
    # If no policy is selected (empty string), show custom options
    show_custom = check_config_id == ""

    return templates.TemplateResponse(
        "partials/repository_check/custom_options.html",
        {
            "request": request,
            "show_custom": show_custom,
        },
    )


@router.get("/update-options", response_class=HTMLResponse)
def update_check_options(
    request: Request,
    check_type: str = "full",
    max_duration: str = "",
    repair_mode: str = "",
):
    """Update check options based on check type selection"""

    # Determine visibility and state based on check type
    if check_type == "repository_only":
        verify_data_disabled = True
        verify_data_opacity = "0.5"
        time_limit_display = "block"
        archive_filters_display = "none"
    else:
        verify_data_disabled = False
        verify_data_opacity = "1"
        time_limit_display = "none"
        archive_filters_display = "block"

    # Handle repair mode conflict with time limits
    repair_mode_checked = repair_mode and repair_mode.lower() in ["true", "on", "1"]
    repair_mode_disabled = bool(max_duration and max_duration.strip())
    if repair_mode_disabled and repair_mode_checked:
        repair_mode_checked = False
        # Note: We can't show notifications in this context, but the conflict is resolved

    return templates.TemplateResponse(
        "partials/repository_check/dynamic_options.html",
        {
            "request": request,
            "verify_data_disabled": verify_data_disabled,
            "verify_data_opacity": verify_data_opacity,
            "time_limit_display": time_limit_display,
            "archive_filters_display": archive_filters_display,
            "repair_mode_checked": repair_mode_checked,
            "repair_mode_disabled": repair_mode_disabled,
            "max_duration": max_duration,
        },
    )


@router.get("/{config_id}", response_model=RepositoryCheckConfigSchema)
def get_repository_check_config(config_id: int, db: Session = Depends(get_db)):
    """Get a specific repository check configuration"""
    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")
    return config


@router.patch("/{config_id}", response_model=RepositoryCheckConfigSchema)
def update_repository_check_config(
    config_id: int,
    update_data: RepositoryCheckConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update a repository check configuration"""

    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")

    # Check for name conflicts if name is being updated
    if update_data.name and update_data.name != config.name:
        existing = (
            db.query(RepositoryCheckConfig)
            .filter(
                RepositoryCheckConfig.name == update_data.name,
                RepositoryCheckConfig.id != config_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="A check policy with this name already exists"
            )

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return config


@router.delete("/{config_id}")
def delete_repository_check_config(
    config_id: int, request: Request, db: Session = Depends(get_db)
):
    """Delete a repository check configuration"""

    config = (
        db.query(RepositoryCheckConfig)
        .filter(RepositoryCheckConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="Check policy not found")

    # TODO: Check if config is in use by any scheduled backups or jobs
    # For now, we'll allow deletion

    db.delete(config)
    db.commit()

    # Return updated HTML list for HTMX requests
    is_htmx_request = "hx-request" in request.headers
    if is_htmx_request:
        configs = (
            db.query(RepositoryCheckConfig).order_by(RepositoryCheckConfig.name).all()
        )
        return templates.TemplateResponse(
            "partials/repository_check/config_list_content.html",
            {"request": request, "configs": configs},
        )

    return {"message": "Check policy deleted successfully"}
