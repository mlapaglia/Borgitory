from fastapi import APIRouter
from . import cloud_sync, s3

router = APIRouter()
router.include_router(cloud_sync.router)

# Include provider-specific endpoints (with provider prefix)
router.include_router(s3.router, prefix="/s3", tags=["s3"])
