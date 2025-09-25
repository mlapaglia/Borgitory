"""
Provider registry system for cloud storage providers.

This module provides a centralized registry for cloud storage providers,
allowing for dynamic discovery and registration of providers without
hardcoded if/elif chains.
"""

import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RcloneMethodMapping:
    """Defines how to map config parameters to rclone method parameters"""

    sync_method: str  # e.g., "sync_repository_to_s3"
    test_method: str  # e.g., "test_s3_connection"
    parameter_mapping: Dict[str, str]  # config_field -> rclone_param
    required_params: List[str]
    optional_params: Optional[Dict[str, object]] = None  # param -> default_value

    def __post_init__(self) -> None:
        if self.optional_params is None:
            self.optional_params = {}


@dataclass
class ProviderMetadata:
    """Metadata about a cloud storage provider"""

    name: str
    label: str
    description: str
    supports_encryption: bool = True
    supports_versioning: bool = False
    requires_credentials: bool = True
    additional_info: Optional[Dict[str, object]] = None
    rclone_mapping: Optional[RcloneMethodMapping] = None

    def __post_init__(self) -> None:
        if self.additional_info is None:
            self.additional_info = {}


@dataclass
class CloudProviderInfo:
    """Complete cloud provider information including metadata."""

    name: str
    label: str
    description: str
    config_class: str
    storage_class: str
    supports_encryption: bool
    supports_versioning: bool
    requires_credentials: bool
    additional_info: Dict[str, object]
    rclone_mapping: Optional[RcloneMethodMapping]


class ProviderRegistry:
    """
    Registry for cloud storage providers.

    Maintains mappings of provider names to their configuration classes,
    storage classes, and metadata.
    """

    def __init__(self) -> None:
        self._config_classes: Dict[str, type] = {}
        self._storage_classes: Dict[str, type] = {}
        self._metadata: Dict[str, ProviderMetadata] = {}

    def register_provider(
        self,
        name: str,
        config_class: type,
        storage_class: type,
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

    def get_config_class(self, provider: str) -> Optional[type]:
        """Get the configuration class for a provider."""
        return self._config_classes.get(provider)

    def get_storage_class(self, provider: str) -> Optional[type]:
        """Get the storage class for a provider."""
        return self._storage_classes.get(provider)

    def get_metadata(self, provider: str) -> Optional[ProviderMetadata]:
        """Get metadata for a provider."""
        return self._metadata.get(provider)

    def get_supported_providers(self) -> List[str]:
        """Get list of all registered provider names."""
        return list(self._config_classes.keys())

    def get_provider_info(self, provider: str) -> Optional[CloudProviderInfo]:
        """
        Get complete provider information including metadata.

        Returns:
            CloudProviderInfo with provider info or None if not found
        """
        if provider not in self._config_classes:
            return None

        metadata = self._metadata.get(provider)
        return CloudProviderInfo(
            name=provider,
            label=metadata.label if metadata else provider.upper(),
            description=metadata.description
            if metadata
            else f"{provider.upper()} storage",
            config_class=self._config_classes[provider].__name__,
            storage_class=self._storage_classes[provider].__name__,
            supports_encryption=metadata.supports_encryption if metadata else True,
            supports_versioning=metadata.supports_versioning if metadata else False,
            requires_credentials=metadata.requires_credentials if metadata else True,
            additional_info=metadata.additional_info
            if metadata and metadata.additional_info
            else {},
            rclone_mapping=metadata.rclone_mapping if metadata else None,
        )

    def get_all_provider_info(self) -> Dict[str, CloudProviderInfo]:
        """Get information for all registered providers."""
        return {
            provider: info
            for provider in self.get_supported_providers()
            if (info := self.get_provider_info(provider)) is not None
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
    label: str = "",
    description: str = "",
    supports_encryption: bool = True,
    supports_versioning: bool = False,
    requires_credentials: bool = True,
    rclone_mapping: Optional[RcloneMethodMapping] = None,
    **metadata_kwargs: object,
) -> Callable[[type], type]:
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

    def decorator(provider_class: type) -> type:
        # Extract config and storage classes from the provider class
        if not hasattr(provider_class, "config_class"):
            raise ValueError(
                f"Provider class {provider_class.__name__} must have 'config_class' attribute"
            )
        if not hasattr(provider_class, "storage_class"):
            raise ValueError(
                f"Provider class {provider_class.__name__} must have 'storage_class' attribute"
            )

        # Auto-discover rclone mapping if not provided
        final_rclone_mapping = rclone_mapping
        storage_class = getattr(provider_class, "storage_class", None)
        if (
            not final_rclone_mapping
            and storage_class
            and hasattr(storage_class, "get_rclone_mapping")
        ):
            try:
                final_rclone_mapping = storage_class.get_rclone_mapping()
                logger.debug(f"Auto-discovered rclone mapping for provider '{name}'")
            except Exception as e:
                logger.warning(
                    f"Failed to auto-discover rclone mapping for provider '{name}': {e}"
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
            rclone_mapping=final_rclone_mapping,
        )

        # Register with global registry
        _registry.register_provider(
            name=name,
            config_class=provider_class.config_class,
            storage_class=provider_class.storage_class,  # type: ignore[attr-defined]
            metadata=metadata,
        )

        return provider_class

    return decorator


# Convenience functions that use the global registry
def get_config_class(provider: str) -> Optional[type]:
    """Get the configuration class for a provider."""
    return _registry.get_config_class(provider)


def get_storage_class(provider: str) -> Optional[type]:
    """Get the storage class for a provider."""
    return _registry.get_storage_class(provider)


def get_metadata(provider: str) -> Optional[ProviderMetadata]:
    """Get metadata for a provider."""
    return _registry.get_metadata(provider)


def get_supported_providers() -> List[str]:
    """Get list of all registered provider names."""
    return _registry.get_supported_providers()


def get_provider_info(provider: str) -> Optional[CloudProviderInfo]:
    """Get complete provider information including metadata."""
    return _registry.get_provider_info(provider)


def get_all_provider_info() -> Dict[str, CloudProviderInfo]:
    """Get information for all registered providers."""
    return _registry.get_all_provider_info()


def is_provider_registered(provider: str) -> bool:
    """
    Check if a provider is registered in the registry.

    Args:
        provider: Provider name to check

    Returns:
        True if provider is registered, False otherwise
    """
    return _registry.is_provider_registered(provider)


def validate_provider_config(provider: str, config_dict: Dict[str, object]) -> None:
    """
    Validate provider configuration using the registered config class.

    Args:
        provider: Provider name (e.g., "s3", "sftp", "smb")
        config_dict: Configuration dictionary to validate

    Raises:
        ValueError: If provider is unknown or configuration is invalid
    """
    if not provider:
        raise ValueError("Provider is required")

    if not config_dict:
        raise ValueError("Configuration is required")

    config_class = get_config_class(provider)
    if not config_class:
        raise ValueError(f"Unknown provider: {provider}")

    try:
        # This will raise validation errors if the config is invalid
        config_class(**config_dict)
    except Exception as e:
        raise ValueError(f"Invalid {provider} configuration: {str(e)}") from e


# Testing utilities
def get_registry() -> ProviderRegistry:
    """Get the global registry instance (mainly for testing)."""
    return _registry


def clear_registry() -> None:
    """Clear all registered providers (for testing only)."""
    global _registry
    _registry._config_classes.clear()
    _registry._storage_classes.clear()
    _registry._metadata.clear()


def validate_rclone_integration(provider: str, rclone_service: object) -> List[str]:
    """
    Validate that provider has proper rclone integration.

    Args:
        provider: Provider name to validate
        rclone_service: Rclone service instance for method validation (required)

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: List[str] = []

    if rclone_service is None:
        errors.append("Rclone service is required for validation")
        return errors

    metadata = get_metadata(provider)
    if not metadata:
        errors.append(f"Provider '{provider}' not registered")
        return errors

    if not metadata.rclone_mapping:
        errors.append(f"Provider '{provider}' has no rclone mapping configured")
        return errors

    mapping = metadata.rclone_mapping

    # Validate required fields
    if not mapping.sync_method:
        errors.append(f"Provider '{provider}' missing sync_method in rclone mapping")

    if not mapping.test_method:
        errors.append(f"Provider '{provider}' missing test_method in rclone mapping")

    if not mapping.parameter_mapping:
        errors.append(
            f"Provider '{provider}' missing parameter_mapping in rclone mapping"
        )

    if not mapping.required_params:
        errors.append(
            f"Provider '{provider}' missing required_params in rclone mapping"
        )

    # Check if rclone methods exist
    try:
        if mapping.sync_method and not hasattr(rclone_service, mapping.sync_method):
            errors.append(f"Rclone sync method '{mapping.sync_method}' not found")

        if mapping.test_method and not hasattr(rclone_service, mapping.test_method):
            errors.append(f"Rclone test method '{mapping.test_method}' not found")

    except Exception as e:
        logger.warning(
            f"Could not validate rclone methods for provider '{provider}': {e}"
        )
        errors.append(f"Error validating rclone methods: {str(e)}")

    return errors
