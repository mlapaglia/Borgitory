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
from app.models.schemas import CleanupConfig as CleanupConfigSchema, CleanupConfigCreate, CleanupConfigUpdate

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

    def update_cleanup_config(
        self, config_id: int, cleanup_config: CleanupConfigUpdate
    ) -> CleanupConfig:
        """Update a cleanup configuration."""
        existing_config = self.get_cleanup_config_by_id(config_id)
        
        # Validate the update
        self._validate_cleanup_config_update(cleanup_config)
        
        # Update fields if provided
        update_data = cleanup_config.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(existing_config, field, value)
        
        self.db.commit()
        self.db.refresh(existing_config)
        return existing_config

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

    def _validate_cleanup_config_update(self, cleanup_config: CleanupConfigUpdate) -> None:
        """Validate cleanup configuration update parameters."""
        if cleanup_config.strategy == "simple" and cleanup_config.keep_within_days is not None and not cleanup_config.keep_within_days:
            raise HTTPException(
                status_code=400, detail="Simple strategy requires keep_within_days"
            )
        elif cleanup_config.strategy == "advanced":
            # Check if any keep_* parameters are being set
            keep_params = [
                cleanup_config.keep_daily,
                cleanup_config.keep_weekly,
                cleanup_config.keep_monthly,
                cleanup_config.keep_yearly,
            ]
            # Only validate if we're setting keep parameters (not None)
            if any(param is not None for param in keep_params) and not any(keep_params):
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
    """Get manual cleanup form with repositories populated"""
    repositories = db.query(Repository).all()

    return templates.TemplateResponse(
        request,
        "partials/cleanup/config_form.html",
        {"repositories": repositories},
    )


@router.get("/policy-form", response_class=HTMLResponse)
async def get_policy_form(
    request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    """Get policy creation form"""
    return templates.TemplateResponse(
        request,
        "partials/cleanup/create_form.html",
        {},
    )


@router.get("/strategy-fields", response_class=HTMLResponse)
async def get_strategy_fields(
    request: Request, strategy: str = "simple"
) -> HTMLResponse:
    """Get dynamic strategy fields based on selection"""
    return templates.TemplateResponse(
        request,
        "partials/cleanup/strategy_fields.html",
        {"strategy": strategy},
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
                request,
                "partials/cleanup/create_success.html",
                {"config_name": cleanup_config.name},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return result

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/create_error.html",
                {"error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        error_msg = f"Failed to create cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/create_error.html",
                {"error_message": error_msg},
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
                request,
                "partials/cleanup/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to enable cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/action_error.html",
                {"error_message": error_message},
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
                request,
                "partials/cleanup/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to disable cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/action_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_cleanup_config_edit_form(
    request: Request,
    config_id: int,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
) -> HTMLResponse:
    """Get edit form for a specific cleanup configuration"""
    try:
        config = cleanup_service.get_cleanup_config_by_id(config_id)
        
        context = {
            "config": config,
            "is_edit_mode": True,
        }

        return templates.TemplateResponse(
            request, "partials/cleanup/edit_form.html", context
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Cleanup configuration not found: {str(e)}")


@router.put("/{config_id}", response_model=CleanupConfigSchema)
async def update_cleanup_config(
    request: Request,
    config_id: int,
    config_update: CleanupConfigUpdate,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Update a cleanup configuration"""
    is_htmx_request = "hx-request" in request.headers
    
    try:
        updated_config = cleanup_service.update_cleanup_config(config_id, config_update)
        
        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cleanup/update_success.html",
                {"config_name": updated_config.name},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return updated_config
            
    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/update_error.html",
                {"error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        error_msg = f"Failed to update cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/update_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


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

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cleanup/delete_success.html",
                {"config_name": config_name},
            )
            response.headers["HX-Trigger"] = "cleanupConfigUpdate"
            return response
        else:
            return {"message": f"Cleanup policy '{config_name}' deleted successfully!"}

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/delete_error.html",
                {"error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        error_message = f"Failed to delete cleanup configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cleanup/delete_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)
