import logging
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from borgitory.dependencies import (
    get_templates,
)
from borgitory.services.cloud_providers.storage.s3_provider_config import (
    S3ProviderConfig,
)
from borgitory.services.cloud_providers.storage.s3_storage import S3Provider

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/providers", response_class=HTMLResponse)
async def get_s3_providers(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get S3 provider options as HTML"""

    providers = [
        {
            "value": provider.value,
            "label": S3ProviderConfig.get_provider_label(provider),
        }
        for provider in S3Provider
    ]
    current_value = request.query_params.get("current_value", "")
    return templates.TemplateResponse(
        request,
        "partials/cloud_sync/providers/s3/s3_provider_options.html",
        {"providers": providers, "selected_provider": current_value},
    )


@router.get("/regions", response_class=HTMLResponse)
async def get_s3_regions(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get S3 regions for a specific provider as HTML"""

    query_params = dict(request.query_params)

    s3_provider = query_params.get("provider_config[provider_type]")
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


@router.get("/storage-classes", response_class=HTMLResponse)
async def get_s3_storage_classes(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get storage classes for a specific S3 provider as HTML"""

    query_params = dict(request.query_params)

    s3_provider = query_params.get("provider_config[provider_type]")
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


@router.get("/endpoint-field", response_class=HTMLResponse)
async def get_s3_endpoint_field(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get endpoint URL field if required for the selected S3 provider"""

    query_params = dict(request.query_params)

    s3_provider = query_params.get("provider_config[provider_type]")
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
