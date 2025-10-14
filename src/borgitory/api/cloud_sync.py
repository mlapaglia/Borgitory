import json
import logging
import os
import re
from typing import Dict, List, Optional, Union, cast, Mapping
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from borgitory.custom_types import ConfigDict
from borgitory.models.database import CloudSyncConfig
from borgitory.models.schemas import (
    CloudSyncConfigCreate,
    CloudSyncConfigUpdate,
    CloudSyncConfig as CloudSyncConfigSchema,
)
from borgitory.dependencies import (
    CloudSyncServiceDep,
    EncryptionServiceDep,
    StorageFactoryDep,
    ProviderRegistryDep,
    get_db,
    get_templates,
    get_browser_timezone_offset,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_supported_providers(registry: ProviderRegistryDep) -> List[Dict[str, str]]:
    """Get supported providers from the registry."""
    provider_info = registry.get_all_provider_info()
    supported_providers = []

    for provider_name, info in provider_info.items():
        supported_providers.append(
            {
                "value": provider_name,
                "label": info.label,
                "description": info.description,
            }
        )

    # Sort by provider name for consistent ordering
    return sorted(supported_providers, key=lambda x: str(x["value"]))


def _get_provider_template(provider: str) -> Optional[str]:
    """Get the appropriate template path for a provider and mode"""
    if not provider:
        return None

    # Validate provider name: only allow alphanumerics, underscores, hyphens
    if not re.fullmatch(r"^[\w-]+$", provider):
        return None

    # Automatically discover templates by checking if they exist on filesystem
    base_templates_dir = os.path.abspath(
        os.path.normpath(
            f"src/borgitory/templates/partials/cloud_sync/providers/{provider}"
        )
    )

    # Fall back to unified template (e.g., s3_fields.html)
    template_path = f"partials/cloud_sync/providers/{provider}/{provider}_fields.html"
    full_path = f"src/borgitory/templates/{template_path}"
    normalized_path = os.path.abspath(os.path.normpath(full_path))

    # Ensure normalized full_path remains inside templates using commonpath
    if os.path.commonpath([base_templates_dir, normalized_path]) != base_templates_dir:
        return None

    if os.path.exists(full_path):
        return template_path

    return None


def _get_submit_button_text(
    registry: ProviderRegistryDep, provider: str, mode: str = "create"
) -> str:
    """Get submit button text using registry information"""
    if not provider:
        if mode == "create":
            return "Add Sync Location"
        else:
            return "Update Sync Location"

    provider_info = registry.get_all_provider_info()
    provider_data = provider_info.get(provider)

    if provider_data:
        provider_label = provider_data.label
        action = "Add" if mode == "create" else "Update"
        return f"{action} {provider_label} Location"
    else:
        # Fallback for unknown providers
        action = "Add" if mode == "create" else "Update"
        return f"{action} Sync Location"


def _get_provider_display_details(
    registry: ProviderRegistryDep, provider: str, provider_config: Dict[str, object]
) -> Dict[str, str]:
    """Get provider display details using registry and storage classes"""
    try:
        storage_class = registry.get_storage_class(provider)
        if storage_class:
            temp_storage = storage_class(None, None, None)
            result = temp_storage.get_display_details(provider_config)
            return cast(Dict[str, str], result)
    except Exception as e:
        logger.warning(f"Error getting display details for provider '{provider}': {e}")

    provider_name = provider.upper() if provider else "Unknown"
    provider_details = "<div><strong>Configuration:</strong> Unknown provider</div>"

    return {"provider_name": provider_name, "provider_details": provider_details}


def _parse_form_data_to_config(
    form_data: Mapping[str, Union[str, object]],
) -> CloudSyncConfigCreate:
    """Parse form data with bracket notation into CloudSyncConfigCreate object"""
    provider_config: ConfigDict = {}
    regular_fields = {}

    for key, value in form_data.items():
        if key.startswith("provider_config[") and key.endswith("]"):
            # Extract field name from provider_config[field_name]
            field_name = key[16:-1]  # Remove "provider_config[" and "]"
            provider_config[field_name] = str(value)
        else:
            regular_fields[key] = str(value)

    # Create the configuration object
    return CloudSyncConfigCreate(
        name=regular_fields["name"],
        provider=regular_fields["provider"],
        path_prefix=regular_fields.get("path_prefix", ""),
        provider_config=provider_config,
    )


def _parse_form_data_to_config_update(
    form_data: Mapping[str, Union[str, object]],
) -> CloudSyncConfigUpdate:
    """Parse form data with bracket notation into CloudSyncConfigUpdate object"""
    provider_config = {}
    regular_fields = {}

    for key, value in form_data.items():
        if key.startswith("provider_config[") and key.endswith("]"):
            # Extract field name from provider_config[field_name]
            field_name = key[16:-1]  # Remove "provider_config[" and "]"
            provider_config[field_name] = str(value)
        else:
            regular_fields[key] = str(value)

    return CloudSyncConfigUpdate(
        name=regular_fields.get("name"),
        provider=regular_fields.get("provider"),
        path_prefix=regular_fields.get("path_prefix"),
        provider_config=cast(ConfigDict, provider_config) if provider_config else None,
    )


@router.get("/form", response_class=HTMLResponse)
async def get_form(
    request: Request,
    registry: ProviderRegistryDep,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get the form for creating a new cloud sync configuration"""
    context = {
        "supported_providers": _get_supported_providers(registry),
        "config": None,
    }
    return templates.TemplateResponse(request, "partials/cloud_sync/form.html", context)


@router.get("/add-form", response_class=HTMLResponse)
async def get_add_form(
    request: Request,
    registry: ProviderRegistryDep,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get the add form (legacy endpoint for backwards compatibility)"""
    return await get_form(request, registry, templates)


@router.get("/provider-fields", response_class=HTMLResponse)
async def get_provider_fields(
    request: Request,
    registry: ProviderRegistryDep,
    provider: str = "",
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get dynamic provider fields based on selection"""
    context = {
        "provider": provider,
        "provider_template": _get_provider_template(provider),
        "submit_text": _get_submit_button_text(registry, provider, "create"),
        "show_submit": provider != "",
    }

    return templates.TemplateResponse(
        request, "partials/cloud_sync/provider_fields.html", context
    )


@router.get("/s3/providers", response_class=HTMLResponse)
async def get_s3_providers(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get S3 provider options as HTML"""
    from borgitory.services.cloud_providers.storage.s3_storage import S3Provider
    from borgitory.services.cloud_providers.storage.s3_provider_config import (
        S3ProviderConfig,
    )

    providers = [
        {
            "value": provider.value,
            "label": S3ProviderConfig.get_provider_label(provider),
        }
        for provider in S3Provider
    ]

    return templates.TemplateResponse(
        request,
        "partials/cloud_sync/providers/s3/s3_provider_options.html",
        {"providers": providers},
    )


@router.get("/s3/regions", response_class=HTMLResponse)
async def get_s3_regions(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get S3 regions for a specific provider as HTML"""
    from borgitory.services.cloud_providers.storage.s3_storage import S3Provider
    from borgitory.services.cloud_providers.storage.s3_provider_config import (
        S3ProviderConfig,
    )

    form_data = await request.form() if request.method == "POST" else {}
    query_params = dict(request.query_params)

    s3_provider = (
        form_data.get("provider_config[provider_type]")
        or query_params.get("s3_provider")
        or query_params.get("provider_config[provider_type]")
        or "AWS"
    )
    current_value = query_params.get("current_value", "")

    try:
        provider_enum = S3Provider(s3_provider)
        regions = S3ProviderConfig.get_regions(provider_enum)
        default_region = S3ProviderConfig.get_default_region(provider_enum)
        selected_region = current_value if current_value else default_region

        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_region_options.html",
            {
                "regions": regions,
                "selected_region": selected_region,
                "has_regions": len(regions) > 0,
            },
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_region_options.html",
            {"regions": [], "selected_region": "us-east-1", "has_regions": False},
        )


@router.get("/s3/storage-classes", response_class=HTMLResponse)
async def get_s3_storage_classes(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get storage classes for a specific S3 provider as HTML"""
    from borgitory.services.cloud_providers.storage.s3_storage import S3Provider
    from borgitory.services.cloud_providers.storage.s3_provider_config import (
        S3ProviderConfig,
    )

    form_data = await request.form() if request.method == "POST" else {}
    query_params = dict(request.query_params)

    s3_provider = (
        form_data.get("provider_config[provider_type]")
        or query_params.get("s3_provider")
        or query_params.get("provider_config[provider]")
        or "AWS"
    )
    current_value = query_params.get("current_value", "")

    try:
        provider_enum = S3Provider(s3_provider)
        storage_classes = S3ProviderConfig.get_storage_classes(provider_enum)
        default_class = S3ProviderConfig.get_default_storage_class(provider_enum)
        selected_class = current_value if current_value else default_class

        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_storage_class_options.html",
            {
                "storage_classes": storage_classes,
                "selected_class": selected_class,
            },
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_storage_class_options.html",
        )


@router.get("/s3/endpoint-field", response_class=HTMLResponse)
async def get_s3_endpoint_field(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get endpoint URL field if required for the selected S3 provider"""
    from borgitory.services.cloud_providers.storage.s3_storage import S3Provider
    from borgitory.services.cloud_providers.storage.s3_provider_config import (
        S3ProviderConfig,
    )

    form_data = await request.form() if request.method == "POST" else {}
    query_params = dict(request.query_params)

    s3_provider = (
        form_data.get("provider_config[provider_type]")
        or query_params.get("s3_provider")
        or query_params.get("provider_config[provider_type]")
        or "AWS"
    )
    current_value = query_params.get("current_value", "")

    try:
        provider_enum = S3Provider(s3_provider)
        requires_endpoint = S3ProviderConfig.requires_endpoint(provider_enum)

        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_endpoint_field.html",
            {
                "requires_endpoint": requires_endpoint,
                "current_value": current_value,
            },
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_endpoint_field.html",
            {"requires_endpoint": False, "current_value": ""},
        )


@router.post("/", response_class=HTMLResponse)
async def create_cloud_sync_config(
    request: Request,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Create a new cloud sync configuration"""
    try:
        form_data = await request.form()
        form_dict = dict(form_data)
        config = _parse_form_data_to_config(form_dict)

        await cloud_sync_service.create_cloud_sync_config(config, db=db)

        response = templates.TemplateResponse(
            request,
            "partials/cloud_sync/create_success.html",
            {"config_name": config.name},
        )
        response.headers["HX-Trigger"] = "cloudSyncUpdate"
        return response

    except ValidationError as e:
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
async def get_cloud_sync_configs_html(
    request: Request,
    registry: ProviderRegistryDep,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Get cloud sync configurations as HTML"""
    try:
        configs_raw = await cloud_sync_service.get_cloud_sync_configs(db)

        # Process configs to add computed fields for template
        processed_configs = []
        for config in configs_raw:
            try:
                provider_config = json.loads(config.provider_config)
            except (json.JSONDecodeError, AttributeError):
                provider_config = {}

            display_info = _get_provider_display_details(
                registry, config.provider, provider_config
            )

            processed_config = config.__dict__.copy()
            processed_config["provider_name"] = display_info["provider_name"]
            processed_config["provider_details"] = display_info["provider_details"]
            processed_configs.append(type("Config", (), processed_config)())

        browser_tz_offset = get_browser_timezone_offset(request)
        return templates.get_template(
            "partials/cloud_sync/config_list_content.html"
        ).render(configs=processed_configs, browser_tz_offset=browser_tz_offset)

    except Exception as e:
        logger.error(f"Error getting cloud sync configurations: {e}")
        return templates.get_template("partials/jobs/error_state.html").render(
            message="Cloud sync feature is initializing... If this persists, try restarting the application.",
            padding="4",
        )


@router.get("/", response_model=List[CloudSyncConfigSchema])
async def list_cloud_sync_configs(
    cloud_sync_service: CloudSyncServiceDep,
    db: AsyncSession = Depends(get_db),
) -> List[CloudSyncConfig]:
    """List all cloud sync configurations"""
    return await cloud_sync_service.get_cloud_sync_configs(db)


@router.get("/{config_id}", response_model=CloudSyncConfigSchema)
async def get_cloud_sync_config(
    config_id: int,
    cloud_sync_service: CloudSyncServiceDep,
    db: AsyncSession = Depends(get_db),
) -> CloudSyncConfig:
    """Get a specific cloud sync configuration"""
    return await cloud_sync_service.get_cloud_sync_config_by_id(config_id, db)


@router.get("/{config_id}/edit", response_class=HTMLResponse)
async def get_cloud_sync_edit_form(
    request: Request,
    config_id: int,
    registry: ProviderRegistryDep,
    encryption_service: EncryptionServiceDep,
    storage_factory: StorageFactoryDep,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get edit form for a specific cloud sync configuration"""
    try:
        decrypted_config = await cloud_sync_service.get_decrypted_config_for_editing(
            config_id, encryption_service, storage_factory, db
        )

        config_obj = type("Config", (), decrypted_config)()

        context = {
            "config": config_obj,
            "provider": decrypted_config["provider"],
            "provider_template": _get_provider_template(decrypted_config["provider"]),
            "supported_providers": _get_supported_providers(registry),
            "is_edit_mode": True,
            "submit_text": _get_submit_button_text(
                registry, decrypted_config["provider"], "edit"
            ),
        }

        return templates.TemplateResponse(
            request, "partials/cloud_sync/form.html", context
        )
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Cloud sync configuration not found: {str(e)}"
        )


@router.put("/{config_id}", response_class=HTMLResponse)
async def update_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Update a cloud sync configuration"""
    try:
        form_data = await request.form()
        form_dict = dict(form_data)
        config_update = _parse_form_data_to_config_update(form_dict)

        result = await cloud_sync_service.update_cloud_sync_config(
            config_id, config_update, db
        )

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
async def delete_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Delete a cloud sync configuration"""

    try:
        config = await cloud_sync_service.get_cloud_sync_config_by_id(config_id, db)
        config_name = config.name
        await cloud_sync_service.delete_cloud_sync_config(config_id, db)
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
    encryption_service: EncryptionServiceDep,
    storage_factory: StorageFactoryDep,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Test a cloud sync configuration"""

    try:
        result = await cloud_sync_service.test_cloud_sync_config(
            config_id, encryption_service, storage_factory, db
        )
        config = await cloud_sync_service.get_cloud_sync_config_by_id(config_id, db)

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
                status_code=200,
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
async def enable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Enable a cloud sync configuration"""

    try:
        config = await cloud_sync_service.enable_cloud_sync_config(config_id, db)
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
async def disable_cloud_sync_config(
    request: Request,
    config_id: int,
    cloud_sync_service: CloudSyncServiceDep,
    templates: Jinja2Templates = Depends(get_templates),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Disable a cloud sync configuration"""

    try:
        config = await cloud_sync_service.disable_cloud_sync_config(config_id, db)
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
