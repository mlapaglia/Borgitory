"""
Cloud Provider Factory and Registry

This module implements the Factory pattern for creating cloud storage providers
and maintains a registry of available providers.
"""

import logging
from typing import Dict, Any, Type, List
from .base import CloudProvider

logger = logging.getLogger(__name__)


class CloudProviderFactory:
    """
    Factory class for creating cloud storage provider instances.
    
    Uses a registry pattern to automatically discover and manage available providers.
    """
    
    _providers: Dict[str, Type[CloudProvider]] = {}
    
    @classmethod
    def register_provider(cls, provider_name: str):
        """
        Decorator to register a cloud provider class.
        
        Args:
            provider_name: Unique identifier for the provider (e.g., 's3', 'sftp')
        """
        def decorator(provider_class: Type[CloudProvider]):
            cls._providers[provider_name] = provider_class
            logger.info(f"Registered cloud provider: {provider_name}")
            return provider_class
        return decorator
    
    @classmethod
    def create_provider(cls, provider_name: str, config: Dict[str, Any], **dependencies) -> CloudProvider:
        """
        Create a provider instance for the specified provider type.
        
        Args:
            provider_name: The name of the provider to create
            config: Configuration dictionary for the provider
            **dependencies: Additional dependencies to inject (e.g., rclone_service=mock_service)
            
        Returns:
            Configured provider instance
            
        Raises:
            ValueError: If the provider is not registered
        """
        if provider_name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unknown provider '{provider_name}'. Available providers: {available}"
            )
        
        provider_class = cls._providers[provider_name]
        return provider_class(config, **dependencies)
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """
        Get a list of all registered provider names.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def is_provider_available(cls, provider_name: str) -> bool:
        """
        Check if a provider is registered and available.
        
        Args:
            provider_name: Name of the provider to check
            
        Returns:
            True if provider is available, False otherwise
        """
        return provider_name in cls._providers
    
    @classmethod
    def get_provider_info(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all registered providers.
        
        Returns:
            Dictionary mapping provider names to their info
        """
        info = {}
        for name, provider_class in cls._providers.items():
            info[name] = {
                "name": name,
                "class_name": provider_class.__name__,
                "module": provider_class.__module__,
            }
        return info
