"""
Registry Factory for creating and managing provider registries.

This module provides factory methods for creating different types of registries
for production and testing scenarios, supporting dependency injection patterns.
"""

from typing import List, Optional
from .registry import ProviderRegistry, get_registry


class RegistryFactory:
    """Factory for creating provider registries with different configurations"""

    @staticmethod
    def create_production_registry() -> ProviderRegistry:
        """
        Create a registry with all production providers registered.

        This automatically discovers and imports all storage modules to register their providers.

        Returns:
            ProviderRegistry: Registry with all production providers
        """
        import importlib
        import pkgutil
        import borgitory.services.cloud_providers.storage as storage_package

        # Automatically discover and import all storage modules
        for importer, modname, ispkg in pkgutil.iter_modules(
            storage_package.__path__, storage_package.__name__ + "."
        ):
            if not ispkg and not modname.endswith(
                ".base"
            ):  # Skip base module and packages
                try:
                    # Import module only if not already imported
                    # The @register_provider decorators will run on first import
                    importlib.import_module(modname)
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to import storage module {modname}: {e}")

        # Return the global registry (which now has providers registered)
        return get_registry()

    @staticmethod
    def create_test_registry(providers: Optional[List[str]] = None) -> ProviderRegistry:
        """
        Create a registry for testing with only specified providers.

        Args:
            providers: List of provider names to register. If None, registers all.

        Returns:
            ProviderRegistry: Clean registry with only specified providers
        """
        from .registry import clear_registry
        import importlib
        import pkgutil
        import borgitory.services.cloud_providers.storage as storage_package

        # Create a fresh registry by clearing and re-registering
        clear_registry()

        if providers is None:
            # Register all providers if none specified
            return RegistryFactory.create_production_registry()

        # Import and register only requested providers
        for importer, modname, ispkg in pkgutil.iter_modules(
            storage_package.__path__, storage_package.__name__ + "."
        ):
            if not ispkg and not modname.endswith(".base"):
                # Extract provider name from module name (e.g., 's3_storage' -> 's3')
                provider_name = modname.split(".")[-1].replace("_storage", "")

                if provider_name in providers:
                    try:
                        # For test registries, we need to reload modules after clearing
                        # to ensure the @register_provider decorators run again
                        module = importlib.import_module(modname)
                        importlib.reload(module)
                    except Exception as e:
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.warning(
                            f"Failed to import storage module {modname}: {e}"
                        )

        return get_registry()

    @staticmethod
    def create_empty_registry() -> ProviderRegistry:
        """
        Create an empty registry for testing scenarios that need no providers.

        Returns:
            ProviderRegistry: Empty registry
        """
        from .registry import clear_registry

        # Clear the registry to ensure it's empty for testing
        clear_registry()
        return get_registry()
