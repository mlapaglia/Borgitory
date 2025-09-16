"""
Provider registry system for cloud storage providers.

This module provides a centralized registry for cloud storage providers,
allowing for dynamic discovery and registration of providers without
hardcoded if/elif chains.
"""

import logging
from typing import Dict, Type, Any, List, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetadata:
    """Metadata about a cloud storage provider"""

    name: str
    label: str
    description: str
    supports_encryption: bool = True
    supports_versioning: bool = False
    requires_credentials: bool = True
    additional_info: Dict[str, Any] = None

    def __post_init__(self):
        if self.additional_info is None:
            self.additional_info = {}


class ProviderRegistry:
    """
    Registry for cloud storage providers.

    Maintains mappings of provider names to their configuration classes,
    storage classes, and metadata.
    """

    def __init__(self):
        self._config_classes: Dict[str, Type] = {}
        self._storage_classes: Dict[str, Type] = {}
        self._metadata: Dict[str, ProviderMetadata] = {}

    def register_provider(
        self,
        name: str,
        config_class: Type,
        storage_class: Type,
        metadata: ProviderMetadata,
    ) -> None:
        """
        Register a provider with the registry.

        Args:
            name: Provider name (e.g., "s3", "sftp", "smb")
            config_class: Pydantic configuration class
            storage_class: Storage implementation class
            metadata: Provider metadata
        """
        if name in self._config_classes:
            logger.warning(f"Provider '{name}' is already registered. Overwriting.")

        self._config_classes[name] = config_class
        self._storage_classes[name] = storage_class
        self._metadata[name] = metadata

        logger.debug(f"Registered provider: {name}")

    def get_config_class(self, provider: str) -> Optional[Type]:
        """Get the configuration class for a provider."""
        return self._config_classes.get(provider)

    def get_storage_class(self, provider: str) -> Optional[Type]:
        """Get the storage class for a provider."""
        return self._storage_classes.get(provider)

    def get_metadata(self, provider: str) -> Optional[ProviderMetadata]:
        """Get metadata for a provider."""
        return self._metadata.get(provider)

    def get_supported_providers(self) -> List[str]:
        """Get list of all registered provider names."""
        return list(self._config_classes.keys())

    def get_provider_info(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get complete provider information including metadata.

        Returns:
            Dictionary with provider info or None if not found
        """
        if provider not in self._config_classes:
            return None

        metadata = self._metadata.get(provider)
        return {
            "name": provider,
            "label": metadata.label if metadata else provider.upper(),
            "description": metadata.description
            if metadata
            else f"{provider.upper()} storage",
            "config_class": self._config_classes[provider].__name__,
            "storage_class": self._storage_classes[provider].__name__,
            "supports_encryption": metadata.supports_encryption if metadata else True,
            "supports_versioning": metadata.supports_versioning if metadata else False,
            "requires_credentials": metadata.requires_credentials if metadata else True,
            "additional_info": metadata.additional_info if metadata else {},
        }

    def get_all_provider_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information for all registered providers."""
        return {
            provider: self.get_provider_info(provider)
            for provider in self.get_supported_providers()
        }

    def is_provider_registered(self, provider: str) -> bool:
        """Check if a provider is registered."""
        return provider in self._config_classes

    def unregister_provider(self, provider: str) -> bool:
        """
        Unregister a provider (mainly for testing).

        Returns:
            True if provider was registered and removed, False otherwise
        """
        if provider not in self._config_classes:
            return False

        del self._config_classes[provider]
        del self._storage_classes[provider]
        if provider in self._metadata:
            del self._metadata[provider]

        logger.debug(f"Unregistered provider: {provider}")
        return True


# Global registry instance
_registry = ProviderRegistry()


def register_provider(
    name: str,
    label: str = None,
    description: str = None,
    supports_encryption: bool = True,
    supports_versioning: bool = False,
    requires_credentials: bool = True,
    **metadata_kwargs,
) -> Callable:
    """
    Decorator to register a provider.

    Usage:
        @register_provider(
            name="s3",
            label="AWS S3",
            description="Amazon S3 compatible storage",
            supports_versioning=True
        )
        class S3Provider:
            config_class = S3StorageConfig
            storage_class = S3Storage

    Args:
        name: Provider name
        label: Display label (defaults to name.upper())
        description: Provider description
        supports_encryption: Whether provider supports encryption
        supports_versioning: Whether provider supports versioning
        requires_credentials: Whether provider requires credentials
        **metadata_kwargs: Additional metadata
    """

    def decorator(provider_class):
        # Extract config and storage classes from the provider class
        if not hasattr(provider_class, "config_class"):
            raise ValueError(
                f"Provider class {provider_class.__name__} must have 'config_class' attribute"
            )
        if not hasattr(provider_class, "storage_class"):
            raise ValueError(
                f"Provider class {provider_class.__name__} must have 'storage_class' attribute"
            )

        # Create metadata
        metadata = ProviderMetadata(
            name=name,
            label=label or name.upper(),
            description=description or f"{name.upper()} storage provider",
            supports_encryption=supports_encryption,
            supports_versioning=supports_versioning,
            requires_credentials=requires_credentials,
            additional_info=metadata_kwargs,
        )

        # Register with global registry
        _registry.register_provider(
            name=name,
            config_class=provider_class.config_class,
            storage_class=provider_class.storage_class,
            metadata=metadata,
        )

        return provider_class

    return decorator


# Convenience functions that use the global registry
def get_config_class(provider: str) -> Optional[Type]:
    """Get the configuration class for a provider."""
    return _registry.get_config_class(provider)


def get_storage_class(provider: str) -> Optional[Type]:
    """Get the storage class for a provider."""
    return _registry.get_storage_class(provider)


def get_metadata(provider: str) -> Optional[ProviderMetadata]:
    """Get metadata for a provider."""
    return _registry.get_metadata(provider)


def get_supported_providers() -> List[str]:
    """Get list of all registered provider names."""
    return _registry.get_supported_providers()


def get_provider_info(provider: str) -> Optional[Dict[str, Any]]:
    """Get complete provider information including metadata."""
    return _registry.get_provider_info(provider)


def get_all_provider_info() -> Dict[str, Dict[str, Any]]:
    """Get information for all registered providers."""
    return _registry.get_all_provider_info()


def is_provider_registered(provider: str) -> bool:
    """Check if a provider is registered."""
    return _registry.is_provider_registered(provider)


# Testing utilities
def get_registry() -> ProviderRegistry:
    """Get the global registry instance (mainly for testing)."""
    return _registry


def clear_registry() -> None:
    """Clear all registered providers (for testing only)."""
    global _registry
    _registry = ProviderRegistry()
