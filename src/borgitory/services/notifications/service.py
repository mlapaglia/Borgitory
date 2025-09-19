"""
Notification service layer.

This module provides the high-level service interface for notification operations,
including configuration validation, provider creation, and encryption handling.
"""

import json
import logging
from typing import Dict, Any, Optional, List

from .types import NotificationMessage, NotificationResult, NotificationConfig
from .registry import get_config_class, get_provider_class, get_supported_providers

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates notification provider configurations"""

    def validate_config(self, provider: str, config: Dict[str, Any]) -> Any:
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

        return config_class(**config)


class NotificationProviderFactory:
    """Factory for creating notification provider instances"""

    def __init__(self) -> None:
        """Initialize notification provider factory."""
        self._validator = ConfigValidator()

    def create_provider(self, provider: str, config: Dict[str, Any]) -> Any:
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

        # Handle the registration wrapper pattern
        if hasattr(provider_class, "__new__") and hasattr(
            provider_class, "config_class"
        ):
            # This is a registration wrapper, call it directly
            provider_instance = provider_class(validated_config)
        else:
            # This is a regular class, instantiate normally
            provider_instance = provider_class(validated_config)

        return provider_instance

    def get_supported_providers(self) -> List[str]:
        """Get list of supported provider names."""
        return get_supported_providers()


class EncryptionService:
    """Handles encryption/decryption of sensitive configuration fields"""

    def encrypt_sensitive_fields(
        self, config: Dict[str, Any], sensitive_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary
            sensitive_fields: List of field names to encrypt

        Returns:
            Configuration with sensitive fields encrypted
        """
        from borgitory.models.database import get_cipher_suite

        encrypted_config = config.copy()
        cipher = get_cipher_suite()

        for field in sensitive_fields:
            if field in encrypted_config and encrypted_config[field]:
                encrypted_value = cipher.encrypt(
                    str(encrypted_config[field]).encode()
                ).decode()
                encrypted_config[f"encrypted_{field}"] = encrypted_value
                del encrypted_config[field]

        return encrypted_config

    def decrypt_sensitive_fields(
        self, config: Dict[str, Any], sensitive_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary with encrypted fields
            sensitive_fields: List of field names to decrypt

        Returns:
            Configuration with sensitive fields decrypted
        """
        from borgitory.models.database import get_cipher_suite

        decrypted_config = config.copy()
        cipher = get_cipher_suite()

        for field in sensitive_fields:
            encrypted_field = f"encrypted_{field}"
            if (
                encrypted_field in decrypted_config
                and decrypted_config[encrypted_field]
            ):
                try:
                    decrypted_value = cipher.decrypt(
                        decrypted_config[encrypted_field].encode()
                    ).decode()
                    decrypted_config[field] = decrypted_value
                    del decrypted_config[encrypted_field]
                except Exception as e:
                    logger.warning(f"Failed to decrypt field '{field}': {e}")
                    # Keep the encrypted field, remove the encrypted_ prefix version
                    del decrypted_config[encrypted_field]

        return decrypted_config


class NotificationService:
    """
    High-level service for notification operations.

    This service coordinates all the components to provide a clean,
    easy-to-test interface for notification functionality.
    """

    def __init__(
        self,
        provider_factory: Optional[NotificationProviderFactory] = None,
        encryption_service: Optional[EncryptionService] = None,
    ) -> None:
        """
        Initialize notification service.

        Args:
            provider_factory: Factory for creating provider instances (optional)
            encryption_service: Service for handling encryption (optional)
        """
        self._provider_factory = provider_factory or NotificationProviderFactory()
        self._encryption_service = encryption_service or EncryptionService()

    async def send_notification(
        self,
        config: NotificationConfig,
        message: NotificationMessage,
    ) -> Any:
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
            provider = self._provider_factory.create_provider(
                config.provider, config.config
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

    async def test_connection(self, config: NotificationConfig) -> Any:
        """
        Test connection to notification service.

        Args:
            config: Notification configuration

        Returns:
            True if connection successful, False otherwise
        """
        try:
            provider = self._provider_factory.create_provider(
                config.provider, config.config
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
            provider = self._provider_factory.create_provider(
                config.provider, config.config
            )
            return str(provider.get_connection_info().endpoint)

        except Exception as e:
            return f"Error getting connection info: {str(e)}"

    def prepare_config_for_storage(self, provider: str, config: Dict[str, Any]) -> str:
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

    def load_config_from_storage(
        self, provider: str, stored_config: str
    ) -> Dict[str, Any]:
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
            if hasattr(config_class, "__fields__"):
                field = config_class.__fields__.get(field_name)
                if field and hasattr(field, "default"):
                    dummy_config[field_name] = field.default
                else:
                    # Use a dummy value based on type
                    if field_name in ["user_key", "app_token", "token", "key"]:
                        dummy_config[field_name] = "dummy_value_30_chars_long_xxx"
                    else:
                        dummy_config[field_name] = "dummy"

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
                "token",
                "password",
                "secret",
                "key",
            ]

        decrypted_config = self._encryption_service.decrypt_sensitive_fields(
            encrypted_config, sensitive_fields
        )

        return decrypted_config
