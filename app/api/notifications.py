"""
API endpoints for managing notification configurations (Pushover, etc.)
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import NotificationConfig, get_db
from app.models.schemas import (
    NotificationConfig as NotificationConfigSchema, 
    NotificationConfigCreate
)
from app.services.pushover_service import pushover_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=NotificationConfigSchema, status_code=status.HTTP_201_CREATED)
async def create_notification_config(notification_config: NotificationConfigCreate, db: Session = Depends(get_db)):
    """Create a new notification configuration"""
    
    db_notification_config = NotificationConfig(
        name=notification_config.name,
        provider=notification_config.provider,
        notify_on_success=notification_config.notify_on_success,
        notify_on_failure=notification_config.notify_on_failure,
        enabled=True
    )
    
    # Encrypt and store credentials
    db_notification_config.set_pushover_credentials(
        notification_config.user_key,
        notification_config.app_token
    )
    
    db.add(db_notification_config)
    db.commit()
    db.refresh(db_notification_config)
    
    return db_notification_config


@router.get("/", response_model=List[NotificationConfigSchema])
def list_notification_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all notification configurations"""
    notification_configs = db.query(NotificationConfig).offset(skip).limit(limit).all()
    return notification_configs


@router.get("/html", response_class=HTMLResponse)
def get_notification_configs_html(db: Session = Depends(get_db)):
    """Get notification configurations as formatted HTML"""
    notification_configs = db.query(NotificationConfig).all()
    
    if not notification_configs:
        return '<div class="text-gray-500 text-sm">No notification configurations</div>'
    
    html_items = []
    for config in notification_configs:
        # Build notification description
        notify_types = []
        if config.notify_on_success:
            notify_types.append("✅ Success")
        if config.notify_on_failure:
            notify_types.append("❌ Failures")
        
        notification_desc = ", ".join(notify_types) if notify_types else "No notifications"
        
        status_class = "bg-green-100 text-green-800" if config.enabled else "bg-gray-100 text-gray-600"
        status_text = "Enabled" if config.enabled else "Disabled"
        
        html_items.append(f"""
            <div class="border rounded-lg p-4 bg-white">
                <div class="flex justify-between items-start mb-2">
                    <h4 class="font-medium text-gray-900">{config.name}</h4>
                    <span class="px-2 py-1 text-xs rounded {status_class}">{status_text}</span>
                </div>
                <p class="text-sm text-gray-600 mb-1">Provider: {config.provider.title()}</p>
                <p class="text-sm text-gray-600 mb-2">Notifications: {notification_desc}</p>
                <div class="flex justify-between items-center text-xs text-gray-500">
                    <span>Created: {config.created_at.strftime('%Y-%m-%d')}</span>
                    <div class="space-x-2">
                        <button onclick="testNotificationConfig({config.id})" 
                                class="text-blue-600 hover:text-blue-800">
                            Test
                        </button>
                        <button onclick="toggleNotificationConfig({config.id}, {str(config.enabled).lower()})" 
                                class="text-blue-600 hover:text-blue-800">
                            {'Disable' if config.enabled else 'Enable'}
                        </button>
                        <button onclick="deleteNotificationConfig({config.id}, '{config.name}')" 
                                class="text-red-600 hover:text-red-800">
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        """)
    
    return ''.join(html_items)


@router.post("/{config_id}/test")
async def test_notification_config(config_id: int, db: Session = Depends(get_db)):
    """Test a notification configuration"""
    notification_config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if not notification_config:
        raise HTTPException(status_code=404, detail="Notification configuration not found")
    
    if notification_config.provider == "pushover":
        user_key, app_token = notification_config.get_pushover_credentials()
        result = await pushover_service.test_pushover_connection(user_key, app_token)
        return result
    else:
        raise HTTPException(status_code=400, detail="Unsupported notification provider")


@router.post("/{config_id}/enable")
async def enable_notification_config(config_id: int, db: Session = Depends(get_db)):
    """Enable a notification configuration"""
    notification_config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if not notification_config:
        raise HTTPException(status_code=404, detail="Notification configuration not found")
    
    notification_config.enabled = True
    db.commit()
    
    return {"message": "Notification configuration enabled successfully"}


@router.post("/{config_id}/disable")
async def disable_notification_config(config_id: int, db: Session = Depends(get_db)):
    """Disable a notification configuration"""
    notification_config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if not notification_config:
        raise HTTPException(status_code=404, detail="Notification configuration not found")
    
    notification_config.enabled = False
    db.commit()
    
    return {"message": "Notification configuration disabled successfully"}


@router.delete("/{config_id}")
async def delete_notification_config(config_id: int, db: Session = Depends(get_db)):
    """Delete a notification configuration"""
    notification_config = db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
    if not notification_config:
        raise HTTPException(status_code=404, detail="Notification configuration not found")
    
    db.delete(notification_config)
    db.commit()
    
    return {"message": "Notification configuration deleted successfully"}