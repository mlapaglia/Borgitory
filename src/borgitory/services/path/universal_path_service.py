"""
Universal path service implementation.

This module provides a single path service implementation that works
across different environments (native Unix, container, future WSL support).
"""

import logging
from pathlib import Path

from borgitory.protocols.path_protocols import PathServiceInterface
from borgitory.services.path.path_configuration_service import PathConfigurationService

logger = logging.getLogger(__name__)


class UniversalPathService(PathServiceInterface):
    """
    Universal path service implementation.

    This service provides filesystem operations that work across different
    environments. It uses pathlib for robust path handling and includes
    security validations.
    """

    def __init__(self, config: PathConfigurationService):
        self.config = config
        logger.info(
            f"Initialized universal path service for {config.get_platform_name()}"
        )

    async def get_data_dir(self) -> str:
        """Get the application data directory."""
        data_dir = self.config.get_base_data_dir()
        await self.ensure_directory(data_dir)
        return data_dir

    async def get_temp_dir(self) -> str:
        """Get the temporary directory."""
        temp_dir = self.config.get_base_temp_dir()
        await self.ensure_directory(temp_dir)
        return temp_dir

    async def get_cache_dir(self) -> str:
        """Get the cache directory."""
        cache_dir = self.config.get_base_cache_dir()
        await self.ensure_directory(cache_dir)
        return cache_dir

    async def get_keyfiles_dir(self) -> str:
        """Get the keyfiles directory."""
        data_dir = await self.get_data_dir()
        keyfiles_dir = self.secure_join(data_dir, "keyfiles")
        await self.ensure_directory(keyfiles_dir)
        return keyfiles_dir

    async def get_mount_base_dir(self) -> str:
        """Get the base directory for archive mounts."""
        temp_dir = await self.get_temp_dir()
        mount_dir = self.secure_join(temp_dir, "borgitory-mounts")
        await self.ensure_directory(mount_dir)
        return mount_dir

    def secure_join(self, base_path: str, *path_parts: str) -> str:
        """
        Securely join path components and validate the result.

        Prevents directory traversal attacks by ensuring the final path
        is within the base directory.
        """
        if not base_path:
            raise ValueError("Base path cannot be empty for secure_join.")

        # Normalize the base path
        validated_base = Path(base_path).resolve()

        # Join path parts without cleaning first (to detect traversal)
        if not path_parts:
            return str(validated_base)

        # Filter out empty parts
        filtered_parts = [part for part in path_parts if part and part.strip()]
        if not filtered_parts:
            return str(validated_base)

        # Join with the validated base
        joined_path = validated_base / Path(*filtered_parts)
        final_path = joined_path.resolve()

        # Validate the final result is still under the base directory
        try:
            final_path.relative_to(validated_base)
        except ValueError:
            logger.error(
                f"Path traversal detected: {final_path} not relative to {validated_base}"
            )
            raise ValueError(
                "Invalid path operation: resulting path is outside the allowed base directory."
            )

        return str(final_path)

    async def ensure_directory(self, path: str) -> None:
        """Ensure a directory exists, creating it if necessary."""
        if not path:
            return

        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {path}")
        except OSError as e:
            logger.error(f"Failed to create directory '{path}': {e}")
            raise

    def get_platform_name(self) -> str:
        """Get the platform name from configuration."""
        return self.config.get_platform_name()
