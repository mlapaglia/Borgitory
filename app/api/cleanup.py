"""
API endpoints for managing cleanup configurations (archive pruning policies)
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.database import CleanupConfig, Repository, get_db
from app.models.schemas import CleanupConfig as CleanupConfigSchema, CleanupConfigCreate

router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


class CleanupService:
    """Service class for cleanup configuration operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_cleanup_config(
        self, cleanup_config: CleanupConfigCreate
    ) -> CleanupConfig:
        """Create a new cleanup configuration."""
        self._validate_cleanup_config(cleanup_config)

        db_cleanup_config = CleanupConfig(
            name=cleanup_config.name,
            strategy=cleanup_config.strategy,
            keep_within_days=cleanup_config.keep_within_days,
            keep_daily=cleanup_config.keep_daily,
            keep_weekly=cleanup_config.keep_weekly,
            keep_monthly=cleanup_config.keep_monthly,
            keep_yearly=cleanup_config.keep_yearly,
            show_list=cleanup_config.show_list,
            show_stats=cleanup_config.show_stats,
            save_space=cleanup_config.save_space,
            enabled=True,
        )

        self.db.add(db_cleanup_config)
        self.db.commit()
        self.db.refresh(db_cleanup_config)

        return db_cleanup_config

    def get_cleanup_configs(
        self, skip: int = 0, limit: int = 100
    ) -> List[CleanupConfig]:
        """Get all cleanup configurations with pagination."""
        return self.db.query(CleanupConfig).offset(skip).limit(limit).all()

    def get_cleanup_config_by_id(self, config_id: int) -> CleanupConfig:
        """Get cleanup configuration by ID."""
        cleanup_config = (
            self.db.query(CleanupConfig).filter(CleanupConfig.id == config_id).first()
        )
        if not cleanup_config:
            raise HTTPException(
                status_code=404, detail="Cleanup configuration not found"
            )
        return cleanup_config

    def enable_cleanup_config(self, config_id: int) -> CleanupConfig:
        """Enable a cleanup configuration."""
        cleanup_config = self.get_cleanup_config_by_id(config_id)
        cleanup_config.enabled = True
        self.db.commit()
        return cleanup_config

    def disable_cleanup_config(self, config_id: int) -> CleanupConfig:
        """Disable a cleanup configuration."""
        cleanup_config = self.get_cleanup_config_by_id(config_id)
        cleanup_config.enabled = False
        self.db.commit()
        return cleanup_config

    def delete_cleanup_config(self, config_id: int) -> None:
        """Delete a cleanup configuration."""
        cleanup_config = self.get_cleanup_config_by_id(config_id)
        self.db.delete(cleanup_config)
        self.db.commit()

    def _validate_cleanup_config(self, cleanup_config: CleanupConfigCreate) -> None:
        """Validate cleanup configuration parameters."""
        if cleanup_config.strategy == "simple" and not cleanup_config.keep_within_days:
            raise HTTPException(
                status_code=400, detail="Simple strategy requires keep_within_days"
            )
        elif cleanup_config.strategy == "advanced":
            if not any(
                [
                    cleanup_config.keep_daily,
                    cleanup_config.keep_weekly,
                    cleanup_config.keep_monthly,
                    cleanup_config.keep_yearly,
                ]
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Advanced strategy requires at least one keep_* parameter",
                )


def get_cleanup_service(db: Session = Depends(get_db)) -> CleanupService:
    """Dependency to get cleanup service instance."""
    return CleanupService(db)


@router.get("/form", response_class=HTMLResponse)
async def get_cleanup_form(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Get cleanup form with repositories populated"""
    repositories = db.query(Repository).all()

    return templates.TemplateResponse(
        request=request,
        name="partials/cleanup/config_form.html",
        context={"repositories": repositories},
    )


@router.get("/strategy-fields", response_class=HTMLResponse)
async def get_strategy_fields(
    request: Request, strategy: str = "simple"
) -> HTMLResponse:
    """Get dynamic strategy fields based on selection"""
    return templates.TemplateResponse(
        request=request,
        name="partials/cleanup/strategy_fields.html",
        context={"strategy": strategy},
    )


@router.post(
    "/", response_model=CleanupConfigSchema, status_code=status.HTTP_201_CREATED
)
async def create_cleanup_config(
    request: Request,
    cleanup_config: CleanupConfigCreate,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Create a new cleanup configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        result = cleanup_service.create_cleanup_config(cleanup_config)

        if is_htmx_request:
            response = templates.TemplateResponse(
                request=request,
                name="partials/cleanup/create_success.html",
                context={"config_name": cleanup_config.name},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return result

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request=request,
                name="partials/cleanup/create_error.html",
                context={"error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        error_msg = f"Failed to create cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request=request,
                name="partials/cleanup/create_error.html",
                context={"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/", response_model=List[CleanupConfigSchema])
def list_cleanup_configs(
    skip: int = 0,
    limit: int = 100,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
) -> List[CleanupConfig]:
    """List all cleanup configurations"""
    return cleanup_service.get_cleanup_configs(skip, limit)


@router.get("/html", response_class=HTMLResponse)
def get_cleanup_configs_html(
    request: Request,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
) -> str:
    """Get cleanup configurations as formatted HTML"""
    try:
        cleanup_configs_raw = cleanup_service.get_cleanup_configs()

        # Process configs to add computed fields for template
        processed_configs = []
        for config in cleanup_configs_raw:
            # Build description based on strategy
            if config.strategy == "simple":
                description = f"Keep archives within {config.keep_within_days} days"
            else:
                parts = []
                if config.keep_daily:
                    parts.append(f"{config.keep_daily} daily")
                if config.keep_weekly:
                    parts.append(f"{config.keep_weekly} weekly")
                if config.keep_monthly:
                    parts.append(f"{config.keep_monthly} monthly")
                if config.keep_yearly:
                    parts.append(f"{config.keep_yearly} yearly")
                description = ", ".join(parts) if parts else "No retention rules"

            # Create processed config object for template
            processed_config = config.__dict__.copy()
            processed_config["description"] = description
            processed_configs.append(type("Config", (), processed_config)())

        return templates.get_template(
            "partials/cleanup/config_list_content.html"
        ).render(request=request, configs=processed_configs)

    except Exception as e:
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading cleanup configurations: {str(e)}", padding="4"
        )


@router.post("/{config_id}/enable", response_model=None)
async def enable_cleanup_config(
    request: Request,
    config_id: int,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Enable a cleanup configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cleanup_service.enable_cleanup_config(config_id)
        message = f"Cleanup policy '{config.name}' enabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_success.html",
                context={"message": message},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to enable cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_error.html",
                context={"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/{config_id}/disable", response_model=None)
async def disable_cleanup_config(
    request: Request,
    config_id: int,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Disable a cleanup configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cleanup_service.disable_cleanup_config(config_id)
        message = f"Cleanup policy '{config.name}' disabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_success.html",
                context={"message": message},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to disable cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_error.html",
                context={"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.delete("/{config_id}", response_model=None)
async def delete_cleanup_config(
    request: Request,
    config_id: int,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Delete a cleanup configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cleanup_service.get_cleanup_config_by_id(config_id)
        config_name = config.name
        cleanup_service.delete_cleanup_config(config_id)
        message = f"Cleanup policy '{config_name}' deleted successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_success.html",
                context={"message": message},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to delete cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request=request,
                name="partials/cleanup/action_error.html",
                context={"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)
