import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import ValidationError

from models.database import get_db
from models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
    CloudSyncConfig as CloudSyncConfigSchema,
)
from services.cloud_sync_service import CloudSyncService
from dependencies import RcloneServiceDep, EncryptionServiceDep, StorageFactoryDep
from services.cloud_providers.registry import get_all_provider_info, get_storage_class

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_supported_providers() -> List[dict]:
    """Get supported providers from the registry."""
    provider_info = get_all_provider_info()
    supported_providers = []

    for provider_name, info in provider_info.items():
        supported_providers.append(
            {
                "value": provider_name,
                "label": info["label"],
                "description": info["description"],
            }
        )

    # Sort by provider name for consistent ordering
    return sorted(supported_providers, key=lambda x: x["value"])


def _get_provider_template(provider: str, mode: str = "create") -> str:
    """Get the appropriate template path for a provider and mode"""
    if not provider:
        return None

    # Check if provider is registered in the registry
    provider_info = get_all_provider_info()
    if provider not in provider_info:
        return None  # Don't try to load template for unknown providers

    suffix = "_edit" if mode == "edit" else ""
    return f"partials/cloud_sync/providers/{provider}_fields{suffix}.html"


def _get_submit_button_text(provider: str, mode: str = "create") -> str:
    """Get submit button text using registry information"""
    if not provider:
        if mode == "create":
            return "Add Sync Location"
        else:
            return "Update Sync Location"

    provider_info = get_all_provider_info()
    provider_data = provider_info.get(provider)

    if provider_data:
        provider_label = provider_data["label"]
        action = "Add" if mode == "create" else "Update"
        return f"{action} {provider_label} Location"
    else:
        # Fallback for unknown providers
        action = "Add" if mode == "create" else "Update"
        return f"{action} Sync Location"


def _get_provider_display_details(provider: str, provider_config: dict) -> dict:
    """Get provider display details using registry and storage classes"""
    try:
        storage_class = get_storage_class(provider)
        if storage_class:
            # Create a temporary instance to call get_display_details
            # We don't need a valid config for this method, just the dict
            temp_storage = storage_class(
                None, None
            )  # rclone_service and config not needed
            return temp_storage.get_display_details(provider_config)
    except Exception as e:
        logger.warning(f"Error getting display details for provider '{provider}': {e}")

    # Fallback to hardcoded behavior for unknown providers
    provider_name = provider.upper() if provider else "Unknown"
    provider_details = "<div><strong>Configuration:</strong> Unknown provider</div>"

    return {"provider_name": provider_name, "provider_details": provider_details}


def _parse_form_data_to_config(form_data) -> CloudSyncConfigCreate:
    """Parse form data with bracket notation into CloudSyncConfigCreate object"""
    provider_config = {}
    regular_fields = {}

    # Parse form data
    for key, value in form_data.items():
        if key.startswith("provider_config[") and key.endswith("]"):
            # Extract field name from provider_config[field_name]
            field_name = key[16:-1]  # Remove "provider_config[" and "]"
            provider_config[field_name] = value
        else:
            regular_fields[key] = value

    # Create the configuration object
    return CloudSyncConfigCreate(
        name=regular_fields["name"],
        provider=regular_fields["provider"],
        path_prefix=regular_fields.get("path_prefix", ""),
        provider_config=provider_config,
    )


def _parse_form_data_to_config_update(form_data) -> CloudSyncConfigUpdate:
    """Parse form data with bracket notation into CloudSyncConfigUpdate object"""
    provider_config = {}
    regular_fields = {}

    # Parse form data
    for key, value in form_data.items():
        if key.startswith("provider_config[") and key.endswith("]"):
            # Extract field name from provider_config[field_name]
            field_name = key[16:-1]  # Remove "provider_config[" and "]"
            provider_config[field_name] = value
        else:
            regular_fields[key] = value

    # Create the configuration object
    return CloudSyncConfigUpdate(
        name=regular_fields.get("name"),
        provider=regular_fields.get("provider"),
        path_prefix=regular_fields.get("path_prefix"),
        provider_config=provider_config if provider_config else None,
    )


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
    context = {
        "supported_providers": _get_supported_providers(),
    }
    return templates.TemplateResponse(
        request, "partials/cloud_sync/add_form.html", context
    )


@router.get("/provider-fields", response_class=HTMLResponse)
async def get_provider_fields(
    request: Request,
    provider: str = "",
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get dynamic provider fields based on selection"""
    context = {
        "provider": provider,
        "provider_template": _get_provider_template(provider, "create"),
        "submit_text": _get_submit_button_text(provider, "create"),
        "show_submit": provider != "",
    }

    return templates.TemplateResponse(
        request, "partials/cloud_sync/provider_fields.html", context
    )


@router.post("/", response_class=HTMLResponse)
async def create_cloud_sync_config(
    request: Request,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Create a new cloud sync configuration"""
    try:
        form_data = await request.form()
        config = _parse_form_data_to_config(form_data)

        cloud_sync_service.create_cloud_sync_config(config)

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_success.html",
            {"config_name": config.name},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except ValidationError as e:
        # Handle Pydantic validation errors (return 422)
        error_msg = f"Validation error: {str(e)}"
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_error.html",
            {"error_message": error_msg},
            status_code=422,
        )
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
            # Parse JSON configuration
            import json

            try:
                provider_config = json.loads(config.provider_config)
            except (json.JSONDecodeError, AttributeError):
                provider_config = {}

            # Generate provider-specific details using registry
            display_info = _get_provider_display_details(
                config.provider, provider_config
            )

            # Create processed config object for template
            processed_config = config.__dict__.copy()
            processed_config["provider_name"] = display_info["provider_name"]
            processed_config["provider_details"] = display_info["provider_details"]
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
    encryption_service: EncryptionServiceDep,
    storage_factory: StorageFactoryDep,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get edit form for a specific cloud sync configuration"""
    try:
        decrypted_config = cloud_sync_service.get_decrypted_config_for_editing(
            config_id, encryption_service, storage_factory
        )

        config_obj = type("Config", (), decrypted_config)()

        context = {
            "config": config_obj,
            "provider": decrypted_config["provider"],
            "provider_template": _get_provider_template(
                decrypted_config["provider"], "edit"
            ),
            "supported_providers": _get_supported_providers(),
            "is_edit_mode": True,
            "submit_text": _get_submit_button_text(
                decrypted_config["provider"], "edit"
            ),
        }

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
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Update a cloud sync configuration"""
    try:
        form_data = await request.form()
        config_update = _parse_form_data_to_config_update(form_data)

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
    encryption_service: EncryptionServiceDep,
    storage_factory: StorageFactoryDep,
    cloud_sync_service: CloudSyncService = Depends(get_cloud_sync_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Test a cloud sync configuration"""

    try:
        result = await cloud_sync_service.test_cloud_sync_config(
            config_id, rclone, encryption_service, storage_factory
        )
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


@router.get("/providers")
def get_supported_providers():
    """Get list of supported cloud providers from the registry."""
    return _get_supported_providers()
