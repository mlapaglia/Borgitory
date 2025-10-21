from fastapi import APIRouter
from . import cloud_sync, s3

from .cloud_sync import _get_supported_providers, _get_provider_display_details

router = APIRouter()
router.include_router(cloud_sync.router)

# Include provider-specific endpoints (with provider prefix)
router.include_router(s3.router, prefix="/s3", tags=["s3"])

__all__ = [
    "_get_supported_providers",
    "_get_provider_display_details",
]
