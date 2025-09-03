from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import CloudSyncConfig, get_db
from app.models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
    CloudSyncConfig as CloudSyncConfigSchema,
    CloudSyncTestRequest
)
from app.services.rclone_service import rclone_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/", response_model=CloudSyncConfigSchema)
async def create_cloud_sync_config(
    config: CloudSyncConfigCreate,
    db: Session = Depends(get_db)
):
    """Create a new cloud sync configuration"""
    # Check if name already exists
    existing = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.name == config.name
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Cloud sync configuration with name '{config.name}' already exists"
        )
    
    # Create new config based on provider type
    db_config = CloudSyncConfig(
        name=config.name,
        provider=config.provider,
        path_prefix=config.path_prefix or ""
    )
    
    if config.provider == "s3":
        # Set S3-specific fields
        db_config.bucket_name = config.bucket_name
        
        # Validate S3 credentials are provided
        if not config.access_key or not config.secret_key:
            raise HTTPException(
                status_code=400,
                detail="S3 configurations require access_key and secret_key"
            )
        
        # Set encrypted S3 credentials
        db_config.set_credentials(config.access_key, config.secret_key)
        
    elif config.provider == "sftp":
        # Set SFTP-specific fields
        db_config.host = config.host
        db_config.port = config.port or 22
        db_config.username = config.username
        db_config.remote_path = config.remote_path
        
        # Validate SFTP required fields
        if not config.host or not config.username or not config.remote_path:
            raise HTTPException(
                status_code=400,
                detail="SFTP configurations require host, username, and remote_path"
            )
        
        # Validate at least password or private key is provided
        if not config.password and not config.private_key:
            raise HTTPException(
                status_code=400,
                detail="SFTP configurations require either password or private_key"
            )
        
        # Set encrypted SFTP credentials
        db_config.set_sftp_credentials(config.password, config.private_key)
        
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {config.provider}. Supported providers: s3, sftp"
        )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    # No longer need to configure rclone remote - we use direct S3 backend
    
    return db_config


@router.get("/html", response_class=HTMLResponse)
def get_cloud_sync_configs_html(request: Request, db: Session = Depends(get_db)):
    """Get cloud sync configurations as HTML"""
    try:
        configs = db.query(CloudSyncConfig).order_by(CloudSyncConfig.created_at.desc()).all()
        
        html_content = ""
        
        if not configs:
            html_content = '''
                <div class="text-gray-500 text-sm py-4 text-center">
                    <p>No cloud sync locations configured.</p>
                    <p class="mt-1">Add one using the form above to automatically sync your repositories to the cloud after each backup.</p>
                </div>
            '''
        else:
            for config in configs:
                status_color = "green" if config.enabled else "red"
                status_text = "Enabled" if config.enabled else "Disabled"
                toggle_text = "Disable" if config.enabled else "Enable"
                
                path_prefix_html = f'<div><strong>Path Prefix:</strong> {config.path_prefix}</div>' if config.path_prefix else ''
                
                # Generate provider-specific details
                if config.provider == "s3":
                    provider_name = "AWS S3"
                    provider_details = f'''
                        <div><strong>Bucket:</strong> {config.bucket_name}</div>
                    '''
                elif config.provider == "sftp":
                    provider_name = "SFTP"
                    provider_details = f'''
                        <div><strong>Host:</strong> {config.host}:{config.port}</div>
                        <div><strong>Username:</strong> {config.username}</div>
                        <div><strong>Remote Path:</strong> {config.remote_path}</div>
                    '''
                else:
                    provider_name = config.provider.upper()
                    provider_details = '<div><strong>Configuration:</strong> Unknown provider</div>'
                
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
                                    <div><strong>Provider:</strong> {provider_name}</div>
                                    {provider_details}
                                    {path_prefix_html}
                                    <div class="text-xs text-gray-500">Created: {config.created_at.strftime("%Y-%m-%d %H:%M")}</div>
                                </div>
                            </div>
                            <div class="flex flex-col space-y-2 ml-4">
                                <button 
                                    onclick="testCloudSyncConnection({config.id}, this)"
                                    class="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 focus:ring-2 focus:ring-blue-500"
                                >
                                    Test
                                </button>
                                <button 
                                    onclick="toggleCloudSyncConfig({config.id}, {str(config.enabled).lower()}, this)"
                                    class="px-3 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 focus:ring-2 focus:ring-gray-500"
                                >
                                    {toggle_text}
                                </button>
                                <button 
                                    onclick="deleteCloudSyncConfig({config.id}, '{config.name}', this)"
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
                <p>Cloud sync feature is initializing...</p>
                <p class="mt-1 text-xs">If this persists, try restarting the application.</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


@router.get("/", response_model=List[CloudSyncConfigSchema])
def list_cloud_sync_configs(db: Session = Depends(get_db)):
    """List all cloud sync configurations"""
    configs = db.query(CloudSyncConfig).all()
    return configs


@router.get("/{config_id}", response_model=CloudSyncConfigSchema)
def get_cloud_sync_config(config_id: int, db: Session = Depends(get_db)):
    """Get a specific cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    return config


@router.put("/{config_id}", response_model=CloudSyncConfigSchema)
async def update_cloud_sync_config(
    config_id: int,
    config_update: CloudSyncConfigUpdate,
    db: Session = Depends(get_db)
):
    """Update a cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    # Check if name is being changed and if it conflicts
    if config_update.name and config_update.name != config.name:
        existing = db.query(CloudSyncConfig).filter(
            CloudSyncConfig.name == config_update.name,
            CloudSyncConfig.id != config_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Cloud sync configuration with name '{config_update.name}' already exists"
            )
    
    # Update fields
    for field, value in config_update.model_dump(exclude_unset=True).items():
        if field in ["access_key", "secret_key", "password", "private_key"]:
            continue  # Handle credentials separately
        setattr(config, field, value)
    
    # Update credentials based on provider type
    if config.provider == "s3":
        # Update S3 credentials if provided
        if config_update.access_key and config_update.secret_key:
            config.set_credentials(config_update.access_key, config_update.secret_key)
    elif config.provider == "sftp":
        # Update SFTP credentials if provided
        if config_update.password or config_update.private_key:
            config.set_sftp_credentials(config_update.password, config_update.private_key)
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    return config


@router.delete("/{config_id}")
def delete_cloud_sync_config(config_id: int, db: Session = Depends(get_db)):
    """Delete a cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    db.delete(config)
    db.commit()
    
    return {"message": f"Cloud sync configuration '{config.name}' deleted successfully"}


@router.post("/{config_id}/test")
async def test_cloud_sync_config(config_id: int, db: Session = Depends(get_db)):
    """Test a cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    # Test the connection based on provider type
    if config.provider == "s3":
        # Get S3 credentials
        access_key, secret_key = config.get_credentials()
        
        result = await rclone_service.test_s3_connection(
            access_key_id=access_key,
            secret_access_key=secret_key,
            bucket_name=config.bucket_name
        )
        
    elif config.provider == "sftp":
        # Get SFTP credentials
        password, private_key = config.get_sftp_credentials()
        
        result = await rclone_service.test_sftp_connection(
            host=config.host,
            username=config.username,
            remote_path=config.remote_path,
            port=config.port or 22,
            password=password if password else None,
            private_key=private_key if private_key else None
        )
        
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider for testing: {config.provider}"
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
def enable_cloud_sync_config(config_id: int, db: Session = Depends(get_db)):
    """Enable a cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    config.enabled = True
    config.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Cloud sync configuration '{config.name}' enabled"}


@router.post("/{config_id}/disable")
def disable_cloud_sync_config(config_id: int, db: Session = Depends(get_db)):
    """Disable a cloud sync configuration"""
    config = db.query(CloudSyncConfig).filter(
        CloudSyncConfig.id == config_id
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Cloud sync configuration not found")
    
    config.enabled = False
    config.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": f"Cloud sync configuration '{config.name}' disabled"}