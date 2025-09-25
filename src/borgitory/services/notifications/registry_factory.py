"""
Registry Factory for creating and managing notification provider registries.

This module provides factory methods for creating different types of registries
for production and testing scenarios, supporting dependency injection patterns.
"""

import importlib
import logging
import pkgutil
from typing import List, Optional, Protocol

import borgitory.services.notifications.providers as providers_package
from .registry import (
    NotificationProviderRegistry,
    get_registry,
    NotificationProviderMetadata,
)

logger = logging.getLogger(__name__)


class NotificationProviderImporter(Protocol):
    """Protocol for importing notification provider modules."""

    def import_all_providers(self) -> None:
        """Import all available notification provider modules."""
        ...

    def import_specific_providers(self, provider_names: List[str]) -> None:
        """Import specific notification provider modules by name."""
        ...


class DefaultNotificationProviderImporter:
    """Default implementation for importing notification provider modules."""

    def import_all_providers(self) -> None:
        """Import all available notification provider modules."""
        for importer, modname, ispkg in pkgutil.iter_modules(
            providers_package.__path__, providers_package.__name__ + "."
        ):
            if not ispkg and not modname.endswith(".__init__"):
                try:
                    importlib.import_module(modname)
                except ImportError as e:
                    logger.warning(
                        f"Could not import notification provider {modname}: {e}"
                    )

    def import_specific_providers(self, provider_names: List[str]) -> None:
        """Import specific notification provider modules by name."""
        for provider_name in provider_names:
            try:
                module_name = f"borgitory.services.notifications.providers.{provider_name}_provider"
                importlib.import_module(module_name)
            except ImportError as e:
                logger.warning(
                    f"Could not import notification provider {provider_name}: {e}"
                )


class NotificationRegistryFactory:
    """Factory for creating notification provider registries with different configurations."""

    def __init__(self, importer: Optional[NotificationProviderImporter] = None):
        """
        Initialize the factory with an optional provider importer.

        Args:
            importer: Provider importer instance. If None, uses default importer.
        """
        self.importer = importer or DefaultNotificationProviderImporter()

    def create_production_registry(self) -> NotificationProviderRegistry:
        """
        Create a registry with all production notification providers registered.

        This automatically discovers and imports all provider modules to register their providers.

        Returns:
            NotificationProviderRegistry: Registry with all production providers
        """
        # Import all providers to ensure they're registered
        self.importer.import_all_providers()

        # Return the global registry which now has all providers registered
        return get_registry()

    def create_test_registry(
        self, provider_names: Optional[List[str]] = None
    ) -> NotificationProviderRegistry:
        """
        Create a clean registry for testing with optional specific providers.

        Args:
            provider_names: Optional list of provider names to include.
                          If None, includes all available providers.

        Returns:
            NotificationProviderRegistry: Clean registry for testing
        """
        # Create a fresh registry instance for testing (don't affect global registry)
        test_registry = NotificationProviderRegistry()

        # Import providers to register them in the global registry temporarily
        # then copy the metadata to our test registry
        if provider_names is not None:
            self.importer.import_specific_providers(provider_names)
        else:
            self.importer.import_all_providers()

        # Copy the registered providers from global registry to test registry
        global_registry = get_registry()
        for provider_name in global_registry.get_supported_providers():
            metadata = global_registry.get_provider_info(provider_name)
            config_class = global_registry.get_config_class(provider_name)
            provider_class = global_registry.get_provider_class(provider_name)

            # Only register if all components are present
            if (
                metadata is not None
                and config_class is not None
                and provider_class is not None
            ):
                test_registry._config_classes[provider_name] = config_class
                test_registry._provider_classes[provider_name] = provider_class
                test_registry._metadata[provider_name] = NotificationProviderMetadata(
                    name=metadata.name,
                    label=metadata.label,
                    description=metadata.description,
                    supports_priority=metadata.supports_priority,
                    supports_attachments=metadata.supports_attachments,
                    supports_formatting=metadata.supports_formatting,
                    requires_credentials=metadata.requires_credentials,
                    additional_info=metadata.additional_info
                    if isinstance(metadata.additional_info, dict)
                    else None,
                )

        return test_registry
