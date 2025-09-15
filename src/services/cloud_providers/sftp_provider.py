"""
SFTP Cloud Storage Provider

This module implements the SFTP provider for syncing Borg repositories to SFTP servers
using rclone.
"""

import logging
from typing import AsyncGenerator, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from .base import CloudProvider, ProviderConfig
from .factory import CloudProviderFactory
from services.rclone_service import RcloneService

logger = logging.getLogger(__name__)


class SFTPConfig(ProviderConfig):
    """Configuration for SFTP provider"""
    
    host: str = Field(..., min_length=1, description="SFTP server hostname or IP")
    username: str = Field(..., min_length=1, description="SFTP username")
    port: int = Field(default=22, ge=1, le=65535, description="SFTP port")
    password: Optional[str] = Field(default=None, description="SFTP password")
    private_key: Optional[str] = Field(default=None, description="SSH private key")
    remote_path: str = Field(..., min_length=1, description="Remote directory path")
    host_key_checking: bool = Field(default=True, description="Enable SSH host key checking")
    
    @field_validator('remote_path')
    @classmethod
    def validate_remote_path(cls, v):
        """Validate remote path format"""
        if not v.startswith('/'):
            v = '/' + v
        return v.rstrip('/')
    
    @model_validator(mode='after')
    def validate_auth_method(self):
        """Ensure at least one authentication method is provided"""
        if not self.password and not self.private_key:
            raise ValueError("Either password or private_key must be provided")
        return self


@CloudProviderFactory.register_provider("sftp")
class SFTPProvider(CloudProvider):
    """SFTP cloud storage provider"""
    
    @property
    def provider_name(self) -> str:
        return "sftp"
    
    def _validate_config(self, config: Dict[str, Any]) -> SFTPConfig:
        """Validate SFTP configuration"""
        return SFTPConfig(**config)
    
    async def sync_repository(
        self,
        repository,
        path_prefix: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Sync repository to SFTP server using rclone.
        
        Args:
            repository: Repository object with path
            path_prefix: Optional path prefix for SFTP destination
            
        Yields:
            Progress updates from rclone sync operation
        """
        logger.info(f"Starting SFTP sync for repository {repository.path} to {self.config.host}:{self.config.remote_path}")
        
        rclone_service = self._get_rclone_service()
        
        try:
            async for progress in rclone_service.sync_repository_to_sftp(
                repository=repository,
                host=self.config.host,
                username=self.config.username,
                remote_path=self.config.remote_path,
                port=self.config.port,
                password=self.config.password,
                private_key=self.config.private_key,
                path_prefix=path_prefix,
            ):
                yield progress
                
        except Exception as e:
            logger.error(f"SFTP sync failed: {str(e)}")
            yield {
                "type": "error",
                "message": f"SFTP sync failed: {str(e)}"
            }
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test SFTP connection and permissions.
        
        Returns:
            Dictionary with test results
        """
        logger.info(f"Testing SFTP connection to {self.config.host}:{self.config.port}")
        
        rclone_service = self._get_rclone_service()
        
        try:
            result = await rclone_service.test_sftp_connection(
                host=self.config.host,
                username=self.config.username,
                remote_path=self.config.remote_path,
                port=self.config.port,
                password=self.config.password,
                private_key=self.config.private_key,
            )
            
            logger.info(f"SFTP connection test result: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"SFTP connection test failed: {str(e)}")
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
        auth_method = "password" if self.config.password else "private_key"
        
        return {
            "provider": self.provider_name,
            "host": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "remote_path": self.config.remote_path,
            "auth_method": auth_method,
            "host_key_checking": self.config.host_key_checking
        }
    
    def _get_sensitive_fields(self) -> list[str]:
        """Return list of sensitive field names"""
        return ["password", "private_key"]
