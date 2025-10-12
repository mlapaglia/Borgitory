import logging
from typing import (
    AsyncGenerator,
    Dict,
    Optional,
    Union,
    cast,
    TypedDict,
)

from borgitory.models.database import Repository
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.services.rclone_types import ConnectionTestResult, ProgressData
from borgitory.protocols.file_protocols import FileServiceProtocol

logger = logging.getLogger(__name__)


class SyncResult(TypedDict, total=False):
    """Type definition for sync operation results"""

    success: bool
    error: Optional[str]
    stats: Optional[Dict[str, Union[str, int, float]]]


class RcloneService:
    def __init__(
        self,
        command_executor: CommandExecutorProtocol,
        file_service: FileServiceProtocol,
    ) -> None:
        self.command_executor = command_executor
        self.file_service = file_service

    async def sync_repository_to_provider(
        self,
        provider: str,
        repository: Repository,
        **provider_config: Union[str, int, bool, None],
    ) -> AsyncGenerator[ProgressData, None]:
        """
        Truly generic provider sync dispatcher using registry.

        Args:
            provider: Provider name (e.g., "s3", "sftp", "smb")
            repository: Repository object to sync
            **provider_config: Provider-specific configuration parameters

        Yields:
            Progress dictionaries from the underlying rclone method

        Raises:
            ValueError: If provider is unknown or has no rclone mapping
        """
        from .cloud_providers.registry import get_metadata

        # Get rclone mapping from registry
        metadata = get_metadata(provider)
        if not metadata or not metadata.rclone_mapping:
            raise ValueError(f"Provider '{provider}' has no rclone mapping configured")

        mapping = metadata.rclone_mapping

        # Get the rclone method
        sync_method = getattr(self, mapping.sync_method, None)
        if not sync_method:
            raise ValueError(f"Rclone method '{mapping.sync_method}' not found")

        # Map parameters from borgitory.config to rclone method parameters
        rclone_params: Dict[str, Union[str, int, bool, Repository, None]] = {
            "repository": repository
        }

        # Apply parameter mapping
        for config_field, rclone_param in mapping.parameter_mapping.items():
            if config_field in provider_config:
                rclone_params[rclone_param] = provider_config[config_field]
            elif config_field == "repository" and config_field in rclone_params:
                # Handle repository -> repository_path conversion
                if rclone_param == "repository_path":
                    rclone_params[rclone_param] = repository.path
                else:
                    rclone_params[rclone_param] = repository

        # Add optional parameters with defaults
        if mapping.optional_params:
            for param, default_value in mapping.optional_params.items():
                if param not in rclone_params:
                    value = provider_config.get(param, default_value)
                    if isinstance(value, (str, int, bool, type(None))):
                        rclone_params[param] = value

        # Remove the original repository key if it was mapped to a different name
        if (
            "repository" in mapping.parameter_mapping
            and "repository" in rclone_params
            and mapping.parameter_mapping["repository"] != "repository"
        ):
            del rclone_params["repository"]

        # Validate required parameters (check mapped parameter names)
        missing_params = []
        for required_param in mapping.required_params:
            # Check if the required param was mapped to a different name
            mapped_param = mapping.parameter_mapping.get(required_param, required_param)
            if mapped_param not in rclone_params:
                missing_params.append(required_param)

        if missing_params:
            raise ValueError(
                f"Missing required parameters for {provider}: {missing_params}"
            )

        # Call the method and yield results
        async for result in sync_method(**rclone_params):
            yield result

    async def test_provider_connection(
        self, provider: str, **provider_config: Union[str, int, bool, None]
    ) -> ConnectionTestResult:
        """
        Generic provider connection test dispatcher using registry.

        Args:
            provider: Provider name (e.g., "s3", "sftp", "smb")
            **provider_config: Provider-specific configuration parameters

        Returns:
            Dictionary with connection test results

        Raises:
            ValueError: If provider is unknown or has no rclone mapping
        """
        from .cloud_providers.registry import get_metadata

        # Get rclone mapping from registry
        metadata = get_metadata(provider)
        if not metadata or not metadata.rclone_mapping:
            raise ValueError(f"Provider '{provider}' has no rclone mapping configured")

        mapping = metadata.rclone_mapping

        # Get the rclone test method
        test_method = getattr(self, mapping.test_method, None)
        if not test_method:
            raise ValueError(f"Rclone test method '{mapping.test_method}' not found")

        # Map parameters from borgitory.config to rclone method parameters
        rclone_params: Dict[str, Union[str, int, bool, None]] = {}

        # Apply parameter mapping
        for config_field, rclone_param in mapping.parameter_mapping.items():
            if config_field in provider_config:
                rclone_params[rclone_param] = provider_config[config_field]

        # Add optional parameters with defaults (excluding repository and path_prefix for connection tests)
        if mapping.optional_params:
            for param, default_value in mapping.optional_params.items():
                if param not in ["path_prefix"] and param not in rclone_params:
                    value = provider_config.get(param, default_value)
                    if isinstance(value, (str, int, bool, type(None))):
                        rclone_params[param] = value

        # Validate required parameters (excluding repository for connection tests)
        test_required_params = [p for p in mapping.required_params if p != "repository"]
        missing_params = [p for p in test_required_params if p not in rclone_params]
        if missing_params:
            raise ValueError(
                f"Missing required parameters for {provider} connection test: {missing_params}"
            )

        # Call the test method
        result = await test_method(**rclone_params)
        return cast(ConnectionTestResult, result)
