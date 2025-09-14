import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from models.database import get_db
from models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
    CloudSyncConfig as CloudSyncConfigSchema,
)
from services.cloud_sync_service import CloudSyncService
from dependencies import RcloneServiceDep

router = APIRouter()
logger = logging.getLogger(__name__)


def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory="src/templates")


def get_cloud_sync_service(db: Session = Depends(get_db)) -> CloudSyncService:
    """Dependency to get cloud sync service instance."""
    return CloudSyncService(db)


@router.get("/add-form", response_class=HTMLResponse)
async def get_add_form(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
) -> HTMLResponse:
    """Get the add form (for cancel functionality)"""
    return templates.TemplateResponse(request, "partials/cloud_sync/add_form.html", {})


@router.get("/provider-fields", response_class=HTMLResponse)
async def get_provider_fields(
    request: Request,
    provider: str = "",
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
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
    elif provider == "":
        context["submit_text"] = "Add Sync Location"
        context["show_submit"] = False
    else:
        context["submit_text"] = "Add Sync Location"
        context["show_submit"] = True

    # Set show_submit flag
    context["show_submit"] = provider != ""

    return templates.TemplateResponse(
        request, "partials/cloud_sync/provider_fields.html", context
    )


@router.post("/", response_class=HTMLResponse)
async def create_cloud_sync_config(
    request: Request,
    config: CloudSyncConfigCreate,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Create a new cloud sync configuration"""
    try:
        cloud_sync_service.create_cloud_sync_config(config)

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_success.html",
            {"config_name": config.name},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_error.html",
            {"error_message": str(e.detail)},
            status_code=e.status_code,
        )
    except Exception as e:
        error_msg = f"Failed to create cloud sync configuration: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.get("/html", response_class=HTMLResponse)
def get_cloud_sync_configs_html(
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
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


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_cloud_sync_edit_form(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get edit form for a specific cloud sync configuration"""
    try:
        config = cloud_sync_service.get_cloud_sync_config_by_id(config_id)

        # Decrypt sensitive fields for editing
        decrypted_config = {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "path_prefix": config.path_prefix,
            "enabled": config.enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

        # Add provider-specific decrypted fields
        if config.provider == "s3":
            decrypted_config["bucket_name"] = config.bucket_name
            if config.encrypted_access_key and config.encrypted_secret_key:
                access_key, secret_key = config.get_credentials()
                decrypted_config["access_key"] = access_key
                decrypted_config["secret_key"] = secret_key
        elif config.provider == "sftp":
            decrypted_config.update(
                {
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "remote_path": config.remote_path,
                }
            )
            if config.encrypted_password or config.encrypted_private_key:
                password, private_key = config.get_sftp_credentials()
                if password:
                    decrypted_config["password"] = password
                if private_key:
                    decrypted_config["private_key"] = private_key

        # Create a simple object for template access
        config_obj = type("Config", (), decrypted_config)()

        context = {
            "config": config_obj,
            "provider": config.provider,
            "is_s3": config.provider == "s3",
            "is_sftp": config.provider == "sftp",
            "is_edit_mode": True,
        }

        # Set submit button text based on provider
        if config.provider == "s3":
            context["submit_text"] = "Update S3 Location"
        elif config.provider == "sftp":
            context["submit_text"] = "Update SFTP Location"
        else:
            context["submit_text"] = "Update Sync Location"

        return templates.TemplateResponse(
            request, "partials/cloud_sync/edit_form.html", context
        )
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Cloud sync configuration not found: {str(e)}"
        )


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_cloud_sync_config(
    request: Request,
    config_id: int,
    config_update: CloudSyncConfigUpdate,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Update a cloud sync configuration"""
    try:
        result = cloud_sync_service.update_cloud_sync_config(config_id, config_update)

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/update_success.html",
            {"config_name": result.name},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/update_error.html",
            {"error_message": str(e.detail)},
            status_code=e.status_code,
        )
    except Exception as e:
        error_msg = f"Failed to update cloud sync configuration: {str(e)}"

        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/update_error.html",
            {"error_message": error_msg},
            status_code=500,
        )


@router.delete("/{config_id}", response_class=HTMLResponse)
def delete_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Delete a cloud sync configuration"""

    try:
        config = cloud_sync_service.get_cloud_sync_config_by_id(config_id)
        config_name = config.name
        cloud_sync_service.delete_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config_name}' deleted successfully!"

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except Exception as e:
        error_message = f"Failed to delete cloud sync configuration: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_error.html",
            {"error_message": error_message},
            status_code=500,
        )


@router.post("/{config_id}/test", response_class=HTMLResponse)
async def test_cloud_sync_config(
    request: Request,
    config_id: int,
    rclone: RcloneServiceDep,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Test a cloud sync configuration"""

    try:
        result = await cloud_sync_service.test_cloud_sync_config(config_id, rclone)
        config = cloud_sync_service.get_cloud_sync_config_by_id(config_id)

        if result["status"] == "success":
            message = f"Successfully connected to {config.name}"
            if result.get("details"):
                message += f" (Read: {result['details'].get('read_test', 'N/A')}, Write: {result['details'].get('write_test', 'N/A')})"

            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/test_success.html",
                {"message": message},
            )
        elif result["status"] == "warning":
            message = f"Connection to {config.name} has issues: {result['message']}"

            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/test_warning.html",
                {"message": message},
            )
        else:
            error_message = f"Connection test failed: {result['message']}"

            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/test_error.html",
                {"error_message": error_message},
                status_code=400,
            )

    except Exception as e:
        error_message = f"Connection test failed: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/test_error.html",
            {"error_message": error_message},
            status_code=500,
        )


@router.post("/{config_id}/enable", response_class=HTMLResponse)
def enable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Enable a cloud sync configuration"""

    try:
        config = cloud_sync_service.enable_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config.name}' enabled successfully!"

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except Exception as e:
        error_message = f"Failed to enable cloud sync: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_error.html",
            {"error_message": error_message},
            status_code=500,
        )


@router.post("/{config_id}/disable", response_class=HTMLResponse)
def disable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Disable a cloud sync configuration"""

    try:
        config = cloud_sync_service.disable_cloud_sync_config(config_id)
        message = f"Cloud sync configuration '{config.name}' disabled successfully!"

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_success.html",
            {"message": message},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except Exception as e:
        error_message = f"Failed to disable cloud sync: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/action_error.html",
            {"error_message": error_message},
            status_code=500,
        )
