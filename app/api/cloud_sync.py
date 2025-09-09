import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
    CloudSyncConfig as CloudSyncConfigSchema,
)
from app.services.cloud_sync_service import CloudSyncService
from app.dependencies import RcloneServiceDep

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def get_cloud_sync_service(db: Session = Depends(get_db)) -> CloudSyncService:
    """Dependency to get cloud sync service instance."""
    return CloudSyncService(db)


@router.get("/provider-fields", response_class=HTMLResponse)
async def get_provider_fields(request: Request, provider: str = "s3") -> HTMLResponse:
    """Get dynamic provider fields based on selection"""
    context = {
        "provider": provider,
        "is_s3": provider == "s3",
        "is_sftp": provider == "sftp",
    }

    # Update submit button text based on provider
    if provider == "s3":
        context["submit_text"] = "Add S3 Location"
    elif provider == "sftp":
        context["submit_text"] = "Add SFTP Location"
    else:
        context["submit_text"] = "Add Sync Location"

    return templates.TemplateResponse(
        request, "partials/cloud_sync/provider_fields.html", context
    )


@router.post("/", response_model=CloudSyncConfigSchema)
async def create_cloud_sync_config(
    request: Request,
    config: CloudSyncConfigCreate,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Create a new cloud sync configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        result = cloud_sync_service.create_cloud_sync_config(config)

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cloud_sync/create_success.html",
                {"config_name": config.name},
            )
            response.headers["HX-Trigger"] = "cloudSyncUpdate"
            return response
        else:
            return result

    except HTTPException as e:
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/create_error.html",
                {"error_message": str(e.detail)},
                status_code=e.status_code,
            )
        raise
    except Exception as e:
        error_msg = f"Failed to create cloud sync configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/create_error.html",
                {"error_message": error_msg},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/html", response_class=HTMLResponse)
def get_cloud_sync_configs_html(
    request: Request,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
) -> str:
    """Get cloud sync configurations as HTML"""
    try:
        configs_raw = cloud_sync_service.get_cloud_sync_configs()

        # Process configs to add computed fields for template
        processed_configs = []
        for config in configs_raw:
            # Generate provider-specific details
            if config.provider == "s3":
                provider_name = "AWS S3"
                provider_details = (
                    f"<div><strong>Bucket:</strong> {config.bucket_name}</div>"
                )
            elif config.provider == "sftp":
                provider_name = "SFTP"
                provider_details = f"""
                    <div><strong>Host:</strong> {config.host}:{config.port}</div>
                    <div><strong>Username:</strong> {config.username}</div>
                    <div><strong>Remote Path:</strong> {config.remote_path}</div>
                """
            else:
                provider_name = config.provider.upper()
                provider_details = (
                    "<div><strong>Configuration:</strong> Unknown provider</div>"
                )

            # Create processed config object for template
            processed_config = config.__dict__.copy()
            processed_config["provider_name"] = provider_name
            processed_config["provider_details"] = provider_details
            processed_configs.append(type("Config", (), processed_config)())

        return templates.get_template(
            "partials/cloud_sync/config_list_content.html"
        ).render(configs=processed_configs)

    except Exception:
        # If there's a database error (like table doesn't exist), return a helpful message
        return templates.get_template("partials/jobs/error_state.html").render(
            message="Cloud sync feature is initializing... If this persists, try restarting the application.",
            padding="4",
        )


@router.get("/", response_model=List[CloudSyncConfigSchema])
def list_cloud_sync_configs(
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """List all cloud sync configurations"""
    return cloud_sync_service.get_cloud_sync_configs()


@router.get("/{config_id}", response_model=CloudSyncConfigSchema)
def get_cloud_sync_config(
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Get a specific cloud sync configuration"""
    return cloud_sync_service.get_cloud_sync_config_by_id(config_id)


@router.put("/{config_id}", response_model=CloudSyncConfigSchema)
async def update_cloud_sync_config(
    config_id: int,
    config_update: CloudSyncConfigUpdate,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Update a cloud sync configuration"""
    return cloud_sync_service.update_cloud_sync_config(config_id, config_update)


@router.delete("/{config_id}", response_model=None)
def delete_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Delete a cloud sync configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cloud_sync_service.get_cloud_sync_config_by_id(config_id)
        config_name = config.name
        cloud_sync_service.delete_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config_name}' deleted successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "cloudSyncUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to delete cloud sync configuration: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/{config_id}/test", response_model=None)
async def test_cloud_sync_config(
    request: Request,
    config_id: int,
    rclone: RcloneServiceDep,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Test a cloud sync configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        result = await cloud_sync_service.test_cloud_sync_config(config_id, rclone)
        config = cloud_sync_service.get_cloud_sync_config_by_id(config_id)

        if result["status"] == "success":
            message = f"Successfully connected to {config.name}"
            if result.get("details"):
                message += f" (Read: {result['details'].get('read_test', 'N/A')}, Write: {result['details'].get('write_test', 'N/A')})"

            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/cloud_sync/test_success.html",
                    {"message": message},
                )
            else:
                return {
                    "status": "success",
                    "message": message,
                    "details": result.get("details", {}),
                    "output": result.get("output", ""),
                }
        elif result["status"] == "warning":
            message = f"Connection to {config.name} has issues: {result['message']}"

            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/cloud_sync/test_warning.html",
                    {"message": message},
                )
            else:
                return {
                    "status": "warning",
                    "message": message,
                    "details": result.get("details", {}),
                    "output": result.get("output", ""),
                }
        else:
            error_message = f"Connection test failed: {result['message']}"
            if is_htmx_request:
                return templates.TemplateResponse(
                    request,
                    "partials/cloud_sync/test_error.html",
                    {"error_message": error_message},
                    status_code=400,
                )
            else:
                raise HTTPException(status_code=400, detail=error_message)

    except Exception as e:
        error_message = f"Connection test failed: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/test_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/{config_id}/enable", response_model=None)
def enable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Enable a cloud sync configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cloud_sync_service.enable_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config.name}' enabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "cloudSyncUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to enable cloud sync: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/{config_id}/disable", response_model=None)
def disable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
):
    """Disable a cloud sync configuration"""
    is_htmx_request = "hx-request" in request.headers

    try:
        config = cloud_sync_service.disable_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config.name}' disabled successfully!"

        if is_htmx_request:
            response = templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_success.html",
                {"message": message},
            )
            response.headers["HX-Trigger"] = "cloudSyncUpdate"
            return response
        else:
            return {"message": message}

    except Exception as e:
        error_message = f"Failed to disable cloud sync: {str(e)}"
        if is_htmx_request:
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/action_error.html",
                {"error_message": error_message},
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)
