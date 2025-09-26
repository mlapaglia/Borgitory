"""
Notification service layer.

This module provides the high-level service interface for notification operations,
including configuration validation, provider creation, and encryption handling.
"""

import inspect
import json
import logging
from typing import (
    Dict,
    Optional,
    List,
    get_type_hints,
    Union,
    get_origin,
    get_args,
    Type,
    cast,
)
from .providers.base import NotificationProvider, NotificationProviderConfig

from .types import NotificationMessage, NotificationResult, NotificationConfig
from .registry import get_config_class, get_provider_class, get_supported_providers
from borgitory.services.encryption_service import EncryptionService
from borgitory.custom_types import ConfigDict

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates notification provider configurations"""

    def validate_config(
        self, provider: str, config: ConfigDict
    ) -> NotificationProviderConfig:
        """
        Validate configuration for a specific provider.

        Args:
            provider: Provider name (e.g., pushover, discord, slack)
            config: Configuration dictionary

        Returns:
            Validated configuration object

        Raises:
            ValueError: If configuration is invalid or provider is unknown
        """
        config_class = get_config_class(provider)
        if config_class is None:
            supported = get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        # Filter out None values for the config class constructor
        filtered_config = {k: v for k, v in config.items() if v is not None}
        return config_class(**filtered_config)  # type: ignore[return-value]


class NotificationProviderFactory:
    """Factory for creating notification provider instances with automatic dependency injection"""

    def __init__(self, http_client: Optional[object] = None) -> None:
        """Initialize notification provider factory with available dependencies."""
        self._validator = ConfigValidator()
        self._dependencies: Dict[str, Union[str, int, float, bool, object]] = {
            "http_client": http_client,
            # Add more injectable dependencies here as needed
        }

    def create_provider(
        self, provider: str, config: ConfigDict
    ) -> NotificationProvider:
        """
        Create a notification provider instance.

        Args:
            provider: Provider name (e.g., pushover, discord, slack)
            config: Configuration dictionary

        Returns:
            NotificationProvider instance

        Raises:
            ValueError: If provider is unknown or config is invalid
        """
        validated_config = self._validator.validate_config(provider, config)

        provider_class = get_provider_class(provider)
        if provider_class is None:
            supported = get_supported_providers()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported providers: {', '.join(sorted(supported))}"
            )

        # Create provider instance with automatic dependency injection
        return self._create_provider_with_dependencies(
            cast(Type[NotificationProvider], provider_class), validated_config
        )

    def _create_provider_with_dependencies(
        self,
        provider_class: Type[NotificationProvider],
        validated_config: NotificationProviderConfig,
    ) -> NotificationProvider:
        """
        Automatically inject dependencies based on constructor signature.

        Uses inspection to determine what dependencies the provider needs
        and injects available ones, with type checking support.
        """
        try:
            # Get constructor signature
            sig = inspect.signature(provider_class.__init__)

            # Get type hints for additional validation
            try:
                type_hints = get_type_hints(provider_class.__init__)
            except (NameError, AttributeError):
                # Some providers might not have complete type hints
                type_hints = {}

            # Build kwargs with available dependencies
            kwargs: Dict[
                str, Union[str, int, float, bool, NotificationProviderConfig, object]
            ] = {"config": validated_config}  # Always pass config

            for param_name, param in sig.parameters.items():
                if param_name in ["self", "config"]:
                    continue

                # Check if we have this dependency available
                if (
                    param_name in self._dependencies
                    and self._dependencies[param_name] is not None
                ):
                    dependency_value = self._dependencies[param_name]

                    # Optional: Type checking if type hints are available
                    if param_name in type_hints:
                        expected_type = type_hints[param_name]

                        # Handle Optional types (Union[SomeType, None])
                        origin = get_origin(expected_type)
                        if origin is Union:
                            args = get_args(expected_type)
                            # Check if this is Optional[T] (Union[T, None])
                            if len(args) == 2 and type(None) in args:
                                # Extract the non-None type
                                expected_type = (
                                    args[0] if args[1] is type(None) else args[1]
                                )

                        # Basic type validation (can be enhanced)
                        try:
                            if not isinstance(dependency_value, expected_type):
                                logger.warning(
                                    f"Type mismatch for {param_name}: expected {expected_type}, "
                                    f"got {type(dependency_value)}. Injecting anyway."
                                )
                        except TypeError:
                            # Some types might not work with isinstance (e.g., generics)
                            logger.debug(
                                f"Cannot validate type for {param_name}, injecting anyway"
                            )

                    kwargs[param_name] = dependency_value
                    logger.debug(
                        f"Injecting {param_name} into {provider_class.__name__}"
                    )

                elif param.default is not param.empty:
                    # Parameter has default value, skip injection
                    logger.debug(f"Skipping {param_name} (has default value)")
                    continue
                else:
                    # Required parameter we don't have
                    logger.warning(
                        f"Required parameter '{param_name}' for {provider_class.__name__} "
                        f"not available in dependencies"
                    )

            return provider_class(**kwargs)  # type: ignore[arg-type]

        except Exception as e:
            logger.error(
                f"Failed to create provider {provider_class.__name__} with DI: {e}"
            )
            raise ValueError(
                f"Could not create provider {provider_class.__name__}: {e}"
            ) from e

    def get_supported_providers(self) -> List[str]:
        """Get list of supported provider names."""
        return get_supported_providers()


class NotificationService:
    """
    High-level service for notification operations.

    This service coordinates all the components to provide a clean,
    easy-to-test interface for notification functionality.
    """

    def __init__(
        self,
        provider_factory: NotificationProviderFactory,
        encryption_service: Optional[EncryptionService] = None,
    ) -> None:
        """
        Initialize notification service with required dependencies.

        Args:
            provider_factory: Factory for creating provider instances (required)
            encryption_service: Service for handling encryption (optional)
        """
        self._provider_factory = provider_factory
        self._encryption_service = encryption_service or EncryptionService()

    async def send_notification(
        self,
        config: NotificationConfig,
        message: NotificationMessage,
    ) -> NotificationResult:
        """
        Send a notification message.

        This is the main entry point for notification operations.
        It handles all the complexity internally and returns a simple result.

        Args:
            config: Notification configuration
            message: Message to send

        Returns:
            NotificationResult indicating success/failure and details
        """
        try:
            # Filter out None values for provider creation
            filtered_config: ConfigDict = {
                k: v for k, v in config.config.items() if v is not None
            }
            provider = self._provider_factory.create_provider(
                config.provider,
                filtered_config,
            )

            return await provider.send_notification(message)

        except Exception as e:
            error_msg = f"Failed to send notification: {str(e)}"
            logger.error(error_msg)
            return NotificationResult(
                success=False,
                provider=config.provider,
                message="Exception occurred",
                error=error_msg,
            )

    async def test_connection(self, config: NotificationConfig) -> bool:
        """
        Test connection to notification service.

        Args:
            config: Notification configuration

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Filter out None values for provider creation
            filtered_config: ConfigDict = {
                k: v for k, v in config.config.items() if v is not None
            }
            provider = self._provider_factory.create_provider(
                config.provider,
                filtered_config,
            )
            return await provider.test_connection()

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False

    def get_connection_info(self, config: NotificationConfig) -> str:
        """
        Get connection information for display.

        Args:
            config: Notification configuration

        Returns:
            String representation of connection info
        """
        try:
            # Filter out None values for provider creation
            filtered_config: ConfigDict = {
                k: v for k, v in config.config.items() if v is not None
            }
            provider = self._provider_factory.create_provider(
                config.provider,
                filtered_config,
            )
            return str(provider.get_connection_info().endpoint)

        except Exception as e:
            return f"Error getting connection info: {str(e)}"

    def prepare_config_for_storage(self, provider: str, config: ConfigDict) -> str:
        """
        Prepare configuration for database storage by encrypting sensitive fields.

        Args:
            provider: Provider name
            config: Configuration dictionary

        Returns:
            JSON string with encrypted sensitive fields
        """
        # Create temporary provider to get sensitive fields
        temp_provider = self._provider_factory.create_provider(provider, config)
        sensitive_fields = temp_provider.get_sensitive_fields()

        encrypted_config = self._encryption_service.encrypt_sensitive_fields(
            config, sensitive_fields
        )

        return json.dumps(encrypted_config)

    def load_config_from_storage(self, provider: str, stored_config: str) -> ConfigDict:
        """
        Load configuration from database storage by decrypting sensitive fields.

        Args:
            provider: Provider name
            stored_config: JSON string with encrypted fields

        Returns:
            Configuration dictionary with decrypted fields
        """
        try:
            encrypted_config = json.loads(stored_config)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in stored configuration: {e}")

        # Create temporary provider to get sensitive fields
        # We need to create it with dummy data first to get the field list
        config_class = get_config_class(provider)
        if not config_class:
            raise ValueError(f"Unknown provider: {provider}")

        # Get sensitive fields from a dummy instance
        dummy_config = {}
        for field_name, field_info in config_class.__annotations__.items():
            if hasattr(config_class, "model_fields"):
                field = config_class.model_fields.get(field_name)
                if field and hasattr(field, "default") and field.default is not None:
                    # Only use default if it's not None/PydanticUndefined
                    from pydantic_core import PydanticUndefined

                    if field.default is not PydanticUndefined:
                        dummy_config[field_name] = field.default
                    else:
                        dummy_config[field_name] = self._generate_dummy_field_value(
                            provider, field_name
                        )
                else:
                    # Use a dummy value based on field name and provider
                    dummy_config[field_name] = self._generate_dummy_field_value(
                        provider, field_name
                    )

        try:
            temp_provider = self._provider_factory.create_provider(
                provider, dummy_config
            )
            sensitive_fields = temp_provider.get_sensitive_fields()
        except Exception:
            # Fallback to common sensitive field names
            sensitive_fields = [
                "user_key",
                "app_token",
                "bot_token",
                "token",
                "password",
                "secret",
                "key",
            ]

        decrypted_config = self._encryption_service.decrypt_sensitive_fields(
            encrypted_config, sensitive_fields
        )

        return decrypted_config

    def _generate_dummy_field_value(self, provider: str, field_name: str) -> str:
        """
        Generate appropriate dummy values for provider fields based on validation requirements.

        Args:
            provider: Provider name (e.g., 'discord', 'pushover')
            field_name: Field name (e.g., 'webhook_url', 'user_key')

        Returns:
            Dummy value that will pass basic validation
        """
        # Provider-specific dummy values
        if provider == "discord":
            if field_name == "webhook_url":
                return "https://discord.com/api/webhooks/123456789012345678/dummy_webhook_token_for_validation_purposes_only"
            elif field_name == "username":
                return "Borgitory"
            elif field_name == "avatar_url":
                return ""

        elif provider == "pushover":
            if field_name in ["user_key", "app_token"]:
                return "dummy_value_30_chars_long_xxx"
            elif field_name == "priority":
                return "0"
            elif field_name == "sound":
                return "default"
            elif field_name == "device":
                return ""

        # Generic fallbacks
        if field_name in [
            "user_key",
            "app_token",
            "token",
            "key",
            "password",
            "secret",
        ]:
            return "dummy_value_30_chars_long_xxx"
        elif field_name in ["priority"]:
            return "0"
        elif field_name in ["url", "webhook_url", "endpoint"]:
            return "https://example.com/dummy"
        else:
            return "dummy"
