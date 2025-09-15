"""
Abstract base class for cloud storage providers.

This module defines the interface that all cloud storage providers must implement
to be compatible with the Borgitory backup system.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional
from pydantic import BaseModel
from models.database import Repository


class ProviderConfig(BaseModel):
    """Base configuration for all cloud providers"""
    
    class Config:
        extra = "forbid"  # Prevent unknown fields


class CloudProvider(ABC):
    """
    Abstract base class for all cloud storage providers.
    
    Each provider must implement methods for:
    - Syncing repositories to the cloud
    - Testing connections
    - Validating configurations
    """
    
    def __init__(self, config: Dict[str, Any], rclone_service=None, **kwargs):
        """
        Initialize the provider with configuration and dependencies.
        
        Args:
            config: Provider-specific configuration dictionary
            rclone_service: Optional RcloneService instance for dependency injection
            **kwargs: Additional dependencies (ignored by default, can be used by subclasses)
        """
        self.config = self._validate_config(config)
        self._rclone_service = rclone_service
        # Store additional dependencies for potential use by subclasses
        self._additional_dependencies = kwargs
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique name identifier for this provider"""
        pass
    
    @abstractmethod
    def _validate_config(self, config: Dict[str, Any]) -> ProviderConfig:
        """
        Validate and parse the provider configuration.
        
        Args:
            config: Raw configuration dictionary
            
        Returns:
            Validated configuration object
            
        Raises:
            ValidationError: If configuration is invalid
        """
        pass
    
    @abstractmethod
    async def sync_repository(
        self,
        repository: Repository,
        path_prefix: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Sync a Borg repository to the cloud storage.
        
        Args:
            repository: The repository to sync
            path_prefix: Optional path prefix for the destination
            
        Yields:
            Progress updates and status information
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to the cloud storage.
        
        Returns:
            Dictionary with status, message, and optional details
        """
        pass
    
    @abstractmethod
    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get sanitized connection information for display.
        
        Returns:
            Dictionary with non-sensitive connection details
        """
        pass
    
    def encrypt_sensitive_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in the configuration.
        
        Args:
            data: Configuration data
            
        Returns:
            Configuration with sensitive fields encrypted
        """
        from models.database import get_cipher_suite
        
        encrypted_data = data.copy()
        sensitive_fields = self._get_sensitive_fields()
        
        cipher = get_cipher_suite()
        for field in sensitive_fields:
            if field in encrypted_data and encrypted_data[field]:
                encrypted_data[f"encrypted_{field}"] = (
                    cipher.encrypt(str(encrypted_data[field]).encode()).decode()
                )
                del encrypted_data[field]
        
        return encrypted_data
    
    def decrypt_sensitive_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in the configuration.
        
        Args:
            data: Configuration data with encrypted fields
            
        Returns:
            Configuration with sensitive fields decrypted
        """
        from models.database import get_cipher_suite
        
        decrypted_data = data.copy()
        sensitive_fields = self._get_sensitive_fields()
        
        cipher = get_cipher_suite()
        for field in sensitive_fields:
            encrypted_field = f"encrypted_{field}"
            if encrypted_field in decrypted_data and decrypted_data[encrypted_field]:
                decrypted_data[field] = (
                    cipher.decrypt(decrypted_data[encrypted_field].encode()).decode()
                )
                del decrypted_data[encrypted_field]
        
        return decrypted_data
    
    @abstractmethod
    def _get_sensitive_fields(self) -> list[str]:
        """
        Return list of field names that contain sensitive data.
        
        Returns:
            List of sensitive field names
        """
        pass
    
    def _get_rclone_service(self):
        """
        Get rclone service instance, creating one if not injected.
        
        Returns:
            RcloneService instance
        """
        if self._rclone_service is None:
            from services.rclone_service import RcloneService
            self._rclone_service = RcloneService()
        return self._rclone_service
