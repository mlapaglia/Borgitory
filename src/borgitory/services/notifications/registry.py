"""
Provider registry system for notification providers.

This module provides a centralized registry for notification providers,
allowing for dynamic discovery and registration of providers without
hardcoded if/elif chains.
"""

import logging
from typing import Dict, Type, List, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NotificationProviderMetadata:
    """Metadata about a notification provider"""

    name: str
    label: str
    description: str
    supports_priority: bool = False
    supports_attachments: bool = False
    supports_formatting: bool = False
    requires_credentials: bool = True
    additional_info: Optional[Dict[str, object]] = None

    def __post_init__(self) -> None:
        if self.additional_info is None:
            self.additional_info = {}


@dataclass
class ProviderInfo:
    """Complete provider information including metadata."""

    name: str
    label: str
    description: str
    config_class: str
    provider_class: str
    supports_priority: bool
    supports_attachments: bool
    supports_formatting: bool
    requires_credentials: bool
    additional_info: Dict[str, object]


class NotificationProviderRegistry:
    """
    Registry for notification providers.

    Maintains mappings of provider names to their configuration classes,
    provider classes, and metadata.
    """

    def __init__(self) -> None:
        self._config_classes: Dict[str, Type[object]] = {}
        self._provider_classes: Dict[str, Type[object]] = {}
        self._metadata: Dict[str, NotificationProviderMetadata] = {}

    def register_provider(
        self,
        name: str,
        config_class: Type[object],
        provider_class: Type[object],
        metadata: NotificationProviderMetadata,
    ) -> None:
        """
        Register a provider with the registry.

        Args:
            name: Provider name (e.g., "pushover", "discord", "slack")
            config_class: Pydantic configuration class
            provider_class: Provider implementation class
            metadata: Provider metadata
        """
        if name in self._config_classes:
            logger.warning(f"Provider '{name}' is already registered. Overwriting.")

        self._config_classes[name] = config_class
        self._provider_classes[name] = provider_class
        self._metadata[name] = metadata

        logger.debug(f"Registered notification provider: {name}")

    def get_config_class(self, provider: str) -> Optional[Type[object]]:
        """Get the configuration class for a provider."""
        return self._config_classes.get(provider)

    def get_provider_class(self, provider: str) -> Optional[Type[object]]:
        """Get the provider class for a provider."""
        return self._provider_classes.get(provider)

    def get_metadata(self, provider: str) -> Optional[NotificationProviderMetadata]:
        """Get metadata for a provider."""
        return self._metadata.get(provider)

    def get_supported_providers(self) -> List[str]:
        """Get list of all registered provider names."""
        return list(self._config_classes.keys())

    def get_provider_info(self, provider: str) -> Optional[ProviderInfo]:
        """
        Get complete provider information including metadata.

        Returns:
            ProviderInfo with provider info or None if not found
        """
        if provider not in self._config_classes:
            return None

        metadata = self._metadata.get(provider)
        return ProviderInfo(
            name=provider,
            label=metadata.label if metadata else provider.upper(),
            description=metadata.description
            if metadata
            else f"{provider.upper()} notifications",
            config_class=self._config_classes[provider].__name__,
            provider_class=self._provider_classes[provider].__name__,
            supports_priority=metadata.supports_priority if metadata else False,
            supports_attachments=metadata.supports_attachments if metadata else False,
            supports_formatting=metadata.supports_formatting if metadata else False,
            requires_credentials=metadata.requires_credentials if metadata else True,
            additional_info=metadata.additional_info
            if metadata and metadata.additional_info
            else {},
        )

    def get_all_provider_info(self) -> Dict[str, ProviderInfo]:
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
        del self._provider_classes[provider]
        if provider in self._metadata:
            del self._metadata[provider]

        logger.debug(f"Unregistered notification provider: {provider}")
        return True


# Global registry instance
_registry = NotificationProviderRegistry()


def register_provider(
    name: str,
    label: str = "",
    description: str = "",
    supports_priority: bool = False,
    supports_attachments: bool = False,
    supports_formatting: bool = False,
    requires_credentials: bool = True,
    **metadata_kwargs: object,
) -> Callable[[Type[object]], Type[object]]:
    """
    Decorator to register a notification provider.

    Usage:
        @register_provider(
            name="pushover",
            label="Pushover",
            description="Push notifications via Pushover service",
            supports_priority=True
        )
        class PushoverProvider:
            config_class = PushoverConfig
            # provider implementation

    Args:
        name: Provider name
        label: Display label (defaults to name.upper())
        description: Provider description
        supports_priority: Whether provider supports priority levels
        supports_attachments: Whether provider supports attachments
        supports_formatting: Whether provider supports rich formatting
        requires_credentials: Whether provider requires credentials
        **metadata_kwargs: Additional metadata
    """

    def decorator(provider_class: Type[object]) -> Type[object]:
        # Extract config class from the provider class
        if not hasattr(provider_class, "config_class"):
            raise ValueError(
                f"Provider class {provider_class.__name__} must have 'config_class' attribute"
            )

        # Create metadata
        metadata = NotificationProviderMetadata(
            name=name,
            label=label or name.upper(),
            description=description or f"{name.upper()} notification provider",
            supports_priority=supports_priority,
            supports_attachments=supports_attachments,
            supports_formatting=supports_formatting,
            requires_credentials=requires_credentials,
            additional_info=metadata_kwargs,
        )

        # Register with global registry
        _registry.register_provider(
            name=name,
            config_class=provider_class.config_class,
            provider_class=provider_class,
            metadata=metadata,
        )

        return provider_class

    return decorator


# Convenience functions that use the global registry
def get_config_class(provider: str) -> Optional[Type[object]]:
    """Get the configuration class for a provider."""
    return _registry.get_config_class(provider)


def get_provider_class(provider: str) -> Optional[Type[object]]:
    """Get the provider class for a provider."""
    return _registry.get_provider_class(provider)


def get_metadata(provider: str) -> Optional[NotificationProviderMetadata]:
    """Get metadata for a provider."""
    return _registry.get_metadata(provider)


def get_supported_providers() -> List[str]:
    """Get list of all registered provider names."""
    return _registry.get_supported_providers()


def get_provider_info(provider: str) -> Optional[ProviderInfo]:
    """Get complete provider information including metadata."""
    return _registry.get_provider_info(provider)


def get_all_provider_info() -> Dict[str, ProviderInfo]:
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
        provider: Provider name (e.g., "pushover", "discord", "slack")
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
def get_registry() -> NotificationProviderRegistry:
    """Get the global registry instance (mainly for testing)."""
    return _registry


def clear_registry() -> None:
    """Clear all registered providers (for testing only)."""
    global _registry
    _registry._config_classes.clear()
    _registry._provider_classes.clear()
    _registry._metadata.clear()
