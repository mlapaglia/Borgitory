"""
Amazon S3 Cloud Storage Provider

This module implements the S3 provider for syncing Borg repositories to Amazon S3
using rclone.
"""

import logging
from typing import AsyncGenerator, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from .base import CloudProvider, ProviderConfig
from .factory import CloudProviderFactory
from services.rclone_service import RcloneService

logger = logging.getLogger(__name__)


class S3Config(ProviderConfig):
    """Configuration for Amazon S3 provider"""
    
    bucket_name: str = Field(..., min_length=1, description="S3 bucket name")
    access_key: str = Field(..., min_length=1, description="AWS access key ID")
    secret_key: str = Field(..., min_length=1, description="AWS secret access key")
    region: str = Field(default="us-east-1", description="AWS region")
    endpoint_url: Optional[str] = Field(default=None, description="Custom S3 endpoint URL")
    storage_class: str = Field(default="STANDARD", description="S3 storage class")
    
    @field_validator('bucket_name')
    @classmethod
    def validate_bucket_name(cls, v):
        """Validate S3 bucket name format"""
        if not v or len(v) < 3 or len(v) > 63:
            raise ValueError("Bucket name must be between 3 and 63 characters")
        return v.lower()
    
    @field_validator('storage_class')
    @classmethod
    def validate_storage_class(cls, v):
        """Validate S3 storage class"""
        valid_classes = [
            "STANDARD", "REDUCED_REDUNDANCY", "STANDARD_IA", "ONEZONE_IA",
            "INTELLIGENT_TIERING", "GLACIER", "DEEP_ARCHIVE"
        ]
        if v.upper() not in valid_classes:
            raise ValueError(f"Invalid storage class. Must be one of: {', '.join(valid_classes)}")
        return v.upper()


@CloudProviderFactory.register_provider("s3")
class S3Provider(CloudProvider):
    """Amazon S3 cloud storage provider"""
    
    @property
    def provider_name(self) -> str:
        return "s3"
    
    def _validate_config(self, config: Dict[str, Any]) -> S3Config:
        """Validate S3 configuration"""
        return S3Config(**config)
    
    async def sync_repository(
        self,
        repository,
        path_prefix: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Sync repository to S3 using rclone.
        
        Args:
            repository: Repository object with path
            path_prefix: Optional path prefix for S3 destination
            
        Yields:
            Progress updates from rclone sync operation
        """
        logger.info(f"Starting S3 sync for repository {repository.path} to bucket {self.config.bucket_name}")
        
        rclone_service = self._get_rclone_service()
        
        try:
            async for progress in rclone_service.sync_repository_to_s3(
                repository=repository,
                access_key_id=self.config.access_key,
                secret_access_key=self.config.secret_key,
                bucket_name=self.config.bucket_name,
                path_prefix=path_prefix,
            ):
                yield progress
                
        except Exception as e:
            logger.error(f"S3 sync failed: {str(e)}")
            yield {
                "type": "error",
                "message": f"S3 sync failed: {str(e)}"
            }
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test S3 connection and permissions.
        
        Returns:
            Dictionary with test results
        """
        logger.info(f"Testing S3 connection to bucket {self.config.bucket_name}")
        
        rclone_service = self._get_rclone_service()
        
        try:
            result = await rclone_service.test_s3_connection(
                access_key_id=self.config.access_key,
                secret_access_key=self.config.secret_key,
                bucket_name=self.config.bucket_name,
            )
            
            logger.info(f"S3 connection test result: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"S3 connection test failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Connection test failed: {str(e)}"
            }
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get sanitized connection information for display.
        
        Returns:
            Dictionary with non-sensitive connection details
        """
        return {
            "provider": self.provider_name,
            "bucket_name": self.config.bucket_name,
            "region": self.config.region,
            "endpoint_url": self.config.endpoint_url,
            "storage_class": self.config.storage_class,
            "access_key_id": f"{self.config.access_key[:4]}***{self.config.access_key[-4:]}" if len(self.config.access_key) > 8 else "***"
        }
    
    def _get_sensitive_fields(self) -> list[str]:
        """Return list of sensitive field names"""
        return ["access_key", "secret_key"]
