"""
API endpoints for managing cleanup configurations (archive pruning policies)
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import CleanupConfig, get_db
from app.models.schemas import (
    CleanupConfig as CleanupConfigSchema, 
    CleanupConfigCreate
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=CleanupConfigSchema, status_code=status.HTTP_201_CREATED)
async def create_cleanup_config(cleanup_config: CleanupConfigCreate, db: Session = Depends(get_db)):
    """Create a new cleanup configuration"""
    
    # Validate that at least one retention parameter is set
    if cleanup_config.strategy == "simple" and not cleanup_config.keep_within_days:
        raise HTTPException(status_code=400, detail="Simple strategy requires keep_within_days")
    elif cleanup_config.strategy == "advanced":
        if not any([cleanup_config.keep_daily, cleanup_config.keep_weekly, 
                   cleanup_config.keep_monthly, cleanup_config.keep_yearly]):
            raise HTTPException(status_code=400, detail="Advanced strategy requires at least one keep_* parameter")
    
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
        enabled=True
    )
    
    db.add(db_cleanup_config)
    db.commit()
    db.refresh(db_cleanup_config)
    
    return db_cleanup_config


@router.get("/", response_model=List[CleanupConfigSchema])
def list_cleanup_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all cleanup configurations"""
    cleanup_configs = db.query(CleanupConfig).offset(skip).limit(limit).all()
    return cleanup_configs


@router.get("/html", response_class=HTMLResponse)
def get_cleanup_configs_html(db: Session = Depends(get_db)):
    """Get cleanup configurations as formatted HTML"""
    cleanup_configs = db.query(CleanupConfig).all()
    
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
        
        status_class = "bg-green-100 text-green-800" if config.enabled else "bg-gray-100 text-gray-600"
        status_text = "Enabled" if config.enabled else "Disabled"
        
        html_items.append(f"""
            <div class="border rounded-lg p-4 bg-white">
                <div class="flex justify-between items-start mb-2">
                    <h4 class="font-medium text-gray-900">{config.name}</h4>
                    <span class="px-2 py-1 text-xs rounded {status_class}">{status_text}</span>
                </div>
                <p class="text-sm text-gray-600 mb-2">{description}</p>
                <div class="flex justify-between items-center text-xs text-gray-500">
                    <span>Created: {config.created_at.strftime('%Y-%m-%d')}</span>
                    <div class="space-x-2">
                        <button onclick="toggleCleanupConfig({config.id}, {str(config.enabled).lower()})" 
                                class="text-blue-600 hover:text-blue-800">
                            {'Disable' if config.enabled else 'Enable'}
                        </button>
                        <button onclick="deleteCleanupConfig({config.id}, '{config.name}')" 
                                class="text-red-600 hover:text-red-800">
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        """)
    
    return ''.join(html_items)


@router.post("/{config_id}/enable")
async def enable_cleanup_config(config_id: int, db: Session = Depends(get_db)):
    """Enable a cleanup configuration"""
    cleanup_config = db.query(CleanupConfig).filter(CleanupConfig.id == config_id).first()
    if not cleanup_config:
        raise HTTPException(status_code=404, detail="Cleanup configuration not found")
    
    cleanup_config.enabled = True
    db.commit()
    
    return {"message": "Cleanup configuration enabled successfully"}


@router.post("/{config_id}/disable")
async def disable_cleanup_config(config_id: int, db: Session = Depends(get_db)):
    """Disable a cleanup configuration"""
    cleanup_config = db.query(CleanupConfig).filter(CleanupConfig.id == config_id).first()
    if not cleanup_config:
        raise HTTPException(status_code=404, detail="Cleanup configuration not found")
    
    cleanup_config.enabled = False
    db.commit()
    
    return {"message": "Cleanup configuration disabled successfully"}


@router.delete("/{config_id}")
async def delete_cleanup_config(config_id: int, db: Session = Depends(get_db)):
    """Delete a cleanup configuration"""
    cleanup_config = db.query(CleanupConfig).filter(CleanupConfig.id == config_id).first()
    if not cleanup_config:
        raise HTTPException(status_code=404, detail="Cleanup configuration not found")
    
    db.delete(cleanup_config)
    db.commit()
    
    return {"message": "Cleanup configuration deleted successfully"}