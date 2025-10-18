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

    # Check if this is a mobile device based on User-Agent
    user_agent = request.headers.get("user-agent", "").lower()
    is_mobile = any(
        keyword in user_agent
        for keyword in ["mobile", "android", "iphone", "ipad", "windows phone"]
    )

    providers = []
    for provider in S3Provider:
        full_label = S3ProviderConfig.get_provider_label(provider)

        # Use shorter labels for mobile devices to prevent overflow
        if is_mobile:
            # Mobile-friendly abbreviated labels
            mobile_labels = {
                S3Provider.AWS: "AWS S3",
                S3Provider.ALIBABA: "Alibaba OSS",
                S3Provider.ARVAN_CLOUD: "Arvan AOS",
                S3Provider.BACKBLAZE: "Backblaze B2",
                S3Provider.CEPH: "Ceph",
                S3Provider.CHINA_MOBILE: "China Mobile EOS",
                S3Provider.CLOUDFLARE: "Cloudflare R2",
                S3Provider.DIGITALOCEAN: "DigitalOcean Spaces",
                S3Provider.DREAMHOST: "Dreamhost Objects",
                S3Provider.EXABA: "Exaba",
                S3Provider.FILELU: "FileLu S5",
                S3Provider.FLASHBLADE: "Pure FlashBlade",
                S3Provider.GCS: "Google Cloud Storage",
                S3Provider.HETZNER: "Hetzner",
                S3Provider.HUAWEI_OBS: "Huawei OBS",
                S3Provider.IBM_COS: "IBM COS",
                S3Provider.IDRIVE: "IDrive e2",
                S3Provider.INTERCOLO: "Intercolo",
                S3Provider.IONOS: "IONOS",
                S3Provider.LYVE_CLOUD: "Seagate Lyve",
                S3Provider.LEVIIA: "Leviia",
                S3Provider.LIARA: "Liara",
                S3Provider.LINODE: "Linode",
                S3Provider.MAGALU: "Magalu",
                S3Provider.MEGA: "MEGA S4",
                S3Provider.MINIO: "MinIO",
                S3Provider.NETEASE: "Netease NOS",
                S3Provider.OUTSCALE: "OUTSCALE OOS",
                S3Provider.OVH_CLOUD: "OVHcloud",
                S3Provider.PETABOX: "Petabox",
                S3Provider.RABATA: "Rabata",
                S3Provider.RACKCORP: "RackCorp",
                S3Provider.RCLONE: "Rclone",
                S3Provider.SCALEWAY: "Scaleway",
                S3Provider.SEAWEEDFS: "SeaweedFS",
                S3Provider.SELECTEL: "Selectel",
                S3Provider.SPECTRA_LOGIC: "Spectra Logic",
                S3Provider.STACKPATH: "StackPath",
                S3Provider.STORJ: "Storj",
                S3Provider.SYNOLOGY: "Synology C2",
                S3Provider.TENCENT_COS: "Tencent COS",
                S3Provider.WASABI: "Wasabi",
                S3Provider.QINIU: "Qiniu Kodo",
                S3Provider.ZATA: "Zata",
                S3Provider.OTHER: "Other S3",
            }
            label = mobile_labels.get(provider, full_label)
        else:
            label = full_label

        providers.append(
            {
                "value": provider.value,
                "label": label,
            }
        )

    # Sort providers by label for consistent ordering
    providers = sorted(providers, key=lambda x: x["label"])
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

    # If no provider specified, default to the first provider (AWS)
    if not s3_provider:
        s3_provider = S3Provider.AWS.value

    try:
        provider_enum = S3Provider(s3_provider)
        regions = S3ProviderConfig.get_regions(provider_enum)
        default_region = S3ProviderConfig.get_default_region(provider_enum)
        selected_region = current_value if current_value else default_region

        if len(regions) > 0:
            # Has regions - show dropdown
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/providers/s3/s3_region_options.html",
                {
                    "regions": regions,
                    "selected_region": selected_region,
                    "has_regions": True,
                    "show_text_field": False,
                },
            )
        else:
            # No regions - show text field
            return templates.TemplateResponse(
                request,
                "partials/cloud_sync/providers/s3/s3_region_options.html",
                {
                    "regions": [],
                    "selected_region": selected_region,
                    "has_regions": False,
                    "show_text_field": True,
                },
            )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_region_options.html",
            {
                "regions": [],
                "selected_region": "us-east-1",
                "has_regions": False,
                "show_text_field": True,
            },
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

    # If no provider specified, default to the first provider (AWS)
    if not s3_provider:
        s3_provider = S3Provider.AWS.value

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

    # If no provider specified, default to the first provider (AWS)
    if not s3_provider:
        s3_provider = S3Provider.AWS.value

    try:
        provider_enum = S3Provider(s3_provider)
        requires_endpoint = S3ProviderConfig.requires_endpoint(provider_enum)
        immutable_endpoint = S3ProviderConfig.has_immutable_endpoint(provider_enum)
        default_endpoint = S3ProviderConfig.get_default_endpoint(provider_enum)

        # Always show endpoint field for all providers
        show_field = True
        # Use current_value if set, else default_endpoint
        value = current_value or default_endpoint

        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_endpoint_field.html",
            {
                "show_field": show_field,
                "requires_endpoint": requires_endpoint,
                "immutable_endpoint": immutable_endpoint,
                "is_optional": not requires_endpoint and not immutable_endpoint,
                "current_value": value,
            },
        )
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/cloud_sync/providers/s3/s3_endpoint_field.html",
            {
                "show_field": False,
                "requires_endpoint": False,
                "immutable_endpoint": False,
                "is_optional": False,
                "current_value": "",
            },
        )
