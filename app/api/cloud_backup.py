from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import CloudBackupConfig, get_db
from app.models.schemas import (
    CloudBackupConfigCreate,
    CloudBackupConfigUpdate,
    CloudBackupConfig as CloudBackupConfigSchema,
    CloudBackupTestRequest
)
from app.services.rclone_service import rclone_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/", response_model=CloudBackupConfigSchema)
async def create_cloud_backup_config(
    config: CloudBackupConfigCreate,
    db: Session = Depends(get_db)
):
    """Create a new cloud backup configuration"""
    # Check if name already exists
    existing = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.name == config.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Cloud backup configuration with name '{config.name}' already exists"
        )
    
    # Create new config
    db_config = CloudBackupConfig(
        name=config.name,
        provider=config.provider,
        region=config.region,
        bucket_name=config.bucket_name,
        path_prefix=config.path_prefix or "",
        endpoint=config.endpoint
    )
    
    # Set encrypted credentials
    db_config.set_credentials(config.access_key, config.secret_key)
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    # No longer need to configure rclone remote - we use direct S3 backend
    
    return db_config


@router.get("/html", response_class=HTMLResponse)
def get_cloud_backup_configs_html(request: Request, db: Session = Depends(get_db)):
    """Get cloud backup configurations as HTML"""
    try:
        configs = db.query(CloudBackupConfig).order_by(CloudBackupConfig.created_at.desc()).all()
        
        html_content = ""
        
        if not configs:
            html_content = '''
                <div class="text-gray-500 text-sm py-4 text-center">
                    <p>No cloud backup locations configured.</p>
                    <p class="mt-1">Add one using the form above to automatically backup your repositories to the cloud after each Borg backup.</p>
                </div>
            '''
        else:
            for config in configs:
                status_color = "green" if config.enabled else "red"
                status_text = "Enabled" if config.enabled else "Disabled"
                toggle_text = "Disable" if config.enabled else "Enable"
                
                path_prefix_html = f'<div><strong>Path Prefix:</strong> {config.path_prefix}</div>' if config.path_prefix else ''
                endpoint_html = f'<div><strong>Endpoint:</strong> {config.endpoint}</div>' if config.endpoint else ''
                
                html_content += f'''
                    <div class="border rounded-lg p-4 mb-3 bg-gray-50">
                        <div class="flex justify-between items-start">
                            <div class="flex-1">
                                <div class="flex items-center mb-2">
                                    <h4 class="font-medium text-gray-900">{config.name}</h4>
                                    <span class="ml-2 px-2 py-1 text-xs rounded-full bg-{status_color}-100 text-{status_color}-800">
                                        {status_text}
                                    </span>
                                </div>
                                <div class="text-sm text-gray-600 space-y-1">
                                    <div><strong>Provider:</strong> AWS S3</div>
                                    <div><strong>Region:</strong> {config.region or "N/A"}</div>
                                    <div><strong>Bucket:</strong> {config.bucket_name}</div>
                                    {path_prefix_html}
                                    {endpoint_html}
                                    <div class="text-xs text-gray-500">Created: {config.created_at.strftime("%Y-%m-%d %H:%M")}</div>
                                </div>
                            </div>
                            <div class="flex flex-col space-y-2 ml-4">
                                <button 
                                    onclick="testCloudBackupConnection({config.id}, this)"
                                    class="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 focus:ring-2 focus:ring-blue-500"
                                >
                                    Test
                                </button>
                                <button 
                                    onclick="toggleCloudBackupConfig({config.id}, {str(config.enabled).lower()}, this)"
                                    class="px-3 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 focus:ring-2 focus:ring-gray-500"
                                >
                                    {toggle_text}
                                </button>
                                <button 
                                    onclick="deleteCloudBackupConfig({config.id}, '{config.name}', this)"
                                    class="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 focus:ring-2 focus:ring-red-500"
                                >
                                    Delete
                                </button>
                            </div>
                        </div>
                    </div>
                '''
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        # If there's a database error (like table doesn't exist), return a helpful message
        error_html = '''
            <div class="text-gray-500 text-sm py-4 text-center">
                <p>Cloud backup feature is initializing...</p>
                <p class="mt-1 text-xs">If this persists, try restarting the application.</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


@router.get("/", response_model=List[CloudBackupConfigSchema])
def list_cloud_backup_configs(db: Session = Depends(get_db)):
    """List all cloud backup configurations"""
    configs = db.query(CloudBackupConfig).all()
    return configs


@router.get("/{config_id}", response_model=CloudBackupConfigSchema)
def get_cloud_backup_config(config_id: int, db: Session = Depends(get_db)):
    """Get a specific cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    return config


@router.put("/{config_id}", response_model=CloudBackupConfigSchema)
async def update_cloud_backup_config(
    config_id: int,
    config_update: CloudBackupConfigUpdate,
    db: Session = Depends(get_db)
):
    """Update a cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    # Check if name is being changed and if it conflicts
    if config_update.name and config_update.name != config.name:
        existing = db.query(CloudBackupConfig).filter(
            CloudBackupConfig.name == config_update.name,
            CloudBackupConfig.id != config_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Cloud backup configuration with name '{config_update.name}' already exists"
            )
    
    # Update fields
    for field, value in config_update.model_dump(exclude_unset=True).items():
        if field in ["access_key", "secret_key"]:
            continue  # Handle credentials separately
        setattr(config, field, value)
    
    # Update credentials if provided
    if config_update.access_key and config_update.secret_key:
        config.set_credentials(config_update.access_key, config_update.secret_key)
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    return config


@router.delete("/{config_id}")
def delete_cloud_backup_config(config_id: int, db: Session = Depends(get_db)):
    """Delete a cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    db.delete(config)
    db.commit()
    
    return {"message": f"Cloud backup configuration '{config.name}' deleted successfully"}


@router.post("/{config_id}/test")
async def test_cloud_backup_config(config_id: int, db: Session = Depends(get_db)):
    """Test a cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    # Get credentials
    access_key, secret_key = config.get_credentials()
    
    # Test the connection
    result = await rclone_service.test_s3_connection(
        access_key_id=access_key,
        secret_access_key=secret_key,
        bucket_name=config.bucket_name,
        region=config.region,
        endpoint=config.endpoint
    )
    
    if result["status"] == "success":
        return {
            "status": "success",
            "message": f"Successfully connected to {config.name}",
            "details": result.get("details", {}),
            "output": result.get("output", "")
        }
    elif result["status"] == "warning":
        return {
            "status": "warning",
            "message": f"Connection to {config.name} has issues: {result['message']}",
            "details": result.get("details", {}),
            "output": result.get("output", "")
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Connection test failed: {result['message']}"
        )


@router.post("/{config_id}/enable")
def enable_cloud_backup_config(config_id: int, db: Session = Depends(get_db)):
    """Enable a cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    config.enabled = True
    config.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Cloud backup configuration '{config.name}' enabled"}


@router.post("/{config_id}/disable")
def disable_cloud_backup_config(config_id: int, db: Session = Depends(get_db)):
    """Disable a cloud backup configuration"""
    config = db.query(CloudBackupConfig).filter(
        CloudBackupConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud backup configuration not found")
    
    config.enabled = False
    config.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Cloud backup configuration '{config.name}' disabled"}