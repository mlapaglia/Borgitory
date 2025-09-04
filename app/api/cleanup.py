"""
API endpoints for managing cleanup configurations (archive pruning policies)
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import CleanupConfig, get_db
from app.models.schemas import CleanupConfig as CleanupConfigSchema, CleanupConfigCreate

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.post(
    "/", response_model=CleanupConfigSchema, status_code=status.HTTP_201_CREATED
)
async def create_cleanup_config(
    cleanup_config: CleanupConfigCreate,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Create a new cleanup configuration"""
    return cleanup_service.create_cleanup_config(cleanup_config)


@router.get("/", response_model=List[CleanupConfigSchema])
def list_cleanup_configs(
    skip: int = 0,
    limit: int = 100,
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """List all cleanup configurations"""
    return cleanup_service.get_cleanup_configs(skip, limit)


@router.get("/html", response_class=HTMLResponse)
def get_cleanup_configs_html(
    cleanup_service: CleanupService = Depends(get_cleanup_service),
):
    """Get cleanup configurations as formatted HTML"""
    cleanup_configs = cleanup_service.get_cleanup_configs()

    if not cleanup_configs:
        return '<div class="text-gray-500 text-sm">No cleanup policies configured</div>'

    html_items = []
    for config in cleanup_configs:
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

        status_class = (
            "bg-green-100 text-green-800"
            if config.enabled
            else "bg-gray-100 text-gray-600"
        )
        status_text = "Enabled" if config.enabled else "Disabled"

        html_items.append(f"""
            <div class="border rounded-lg p-4 bg-white">
                <div class="flex justify-between items-start mb-2">
                    <h4 class="font-medium text-gray-900">{config.name}</h4>
                    <span class="px-2 py-1 text-xs rounded {status_class}">{status_text}</span>
                </div>
                <p class="text-sm text-gray-600 mb-2">{description}</p>
                <div class="flex justify-between items-center text-xs text-gray-500">
                    <span>Created: {config.created_at.strftime("%Y-%m-%d")}</span>
                    <div class="space-x-2">
                        <button onclick="toggleCleanupConfig({config.id}, {str(config.enabled).lower()})" 
                                class="text-blue-600 hover:text-blue-800">
                            {"Disable" if config.enabled else "Enable"}
                        </button>
                        <button onclick="deleteCleanupConfig({config.id}, '{config.name}')" 
                                class="text-red-600 hover:text-red-800">
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        """)

    return "".join(html_items)


@router.post("/{config_id}/enable")
async def enable_cleanup_config(
    config_id: int, cleanup_service: CleanupService = Depends(get_cleanup_service)
):
    """Enable a cleanup configuration"""
    cleanup_service.enable_cleanup_config(config_id)
    return {"message": "Cleanup configuration enabled successfully"}


@router.post("/{config_id}/disable")
async def disable_cleanup_config(
    config_id: int, cleanup_service: CleanupService = Depends(get_cleanup_service)
):
    """Disable a cleanup configuration"""
    cleanup_service.disable_cleanup_config(config_id)
    return {"message": "Cleanup configuration disabled successfully"}


@router.delete("/{config_id}")
async def delete_cleanup_config(
    config_id: int, cleanup_service: CleanupService = Depends(get_cleanup_service)
):
    """Delete a cleanup configuration"""
    cleanup_service.delete_cleanup_config(config_id)
    return {"message": "Cleanup configuration deleted successfully"}
