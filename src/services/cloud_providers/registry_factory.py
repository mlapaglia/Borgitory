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

        This triggers import of all storage modules to register their providers.

        Returns:
            ProviderRegistry: Registry with all production providers
        """
        # Import storage modules to trigger provider registration
        import importlib
        from . import storage

        # Force reload to ensure registration happens
        importlib.reload(storage.s3_storage)
        importlib.reload(storage.sftp_storage)
        importlib.reload(storage.smb_storage)

        # Return the global registry (which now has providers registered)
        return get_registry()

    @staticmethod
    def create_test_registry(providers: Optional[List[str]] = None) -> ProviderRegistry:
        """
        Create a registry for testing with only specified providers.

        Args:
            providers: List of provider names to register. If None, registers all.
                      Supported: ['s3', 'sftp', 'smb']

        Returns:
            ProviderRegistry: Clean registry with only specified providers
        """
        from .registry import clear_registry

        # Create a fresh registry by clearing and re-registering
        clear_registry()

        if providers is None:
            providers = ["s3", "sftp", "smb"]

        # Import and register only requested providers
        import importlib
        from . import storage

        if "s3" in providers:
            importlib.reload(storage.s3_storage)

        if "sftp" in providers:
            importlib.reload(storage.sftp_storage)

        if "smb" in providers:
            importlib.reload(storage.smb_storage)

        return get_registry()

    @staticmethod
    def create_empty_registry() -> ProviderRegistry:
        """
        Create an empty registry for testing scenarios that need no providers.

        Returns:
            ProviderRegistry: Empty registry
        """
        from .registry import clear_registry

        clear_registry()
        return get_registry()

    @staticmethod
    def get_default_registry() -> ProviderRegistry:
        """
        Get the default registry (production registry).

        This is the fallback for backward compatibility when no registry is injected.

        Returns:
            ProviderRegistry: The default global registry
        """
        return get_registry()
