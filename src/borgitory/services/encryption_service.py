"""
Shared encryption service for all sensitive configuration fields.

This service provides encryption/decryption capabilities for both cloud provider
and notification service configurations, eliminating code duplication and
providing a single source of truth for encryption operations.
"""

import logging
from typing import List
from borgitory.custom_types import ConfigDict

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Handles encryption/decryption of sensitive configuration fields for all services.

    This service is used by both cloud provider and notification services to
    encrypt/decrypt sensitive fields like API keys, passwords, and tokens.

    Uses the application's cipher suite for consistent encryption across all domains.
    """

    def encrypt_sensitive_fields(
        self,
        config: ConfigDict,
        sensitive_fields: List[str],
    ) -> ConfigDict:
        """
        Encrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary containing sensitive fields
            sensitive_fields: List of field names that should be encrypted

        Returns:
            Configuration dictionary with sensitive fields encrypted and renamed
            to 'encrypted_{field_name}' format

        Example:
            >>> service = EncryptionService()
            >>> config = {"api_key": "secret123", "timeout": 30}
            >>> encrypted = service.encrypt_sensitive_fields(config, ["api_key"])
            >>> # Result: {"encrypted_api_key": "...", "timeout": 30}
        """
        from borgitory.models.database import get_cipher_suite

        encrypted_config = config.copy()
        cipher = get_cipher_suite()

        for field in sensitive_fields:
            if field in encrypted_config and encrypted_config[field]:
                field_value = encrypted_config[field]
                encrypted_value = cipher.encrypt(str(field_value).encode()).decode()
                encrypted_config[f"encrypted_{field}"] = encrypted_value
                del encrypted_config[field]

        return encrypted_config

    def decrypt_sensitive_fields(
        self,
        config: ConfigDict,
        sensitive_fields: List[str],
    ) -> ConfigDict:
        """
        Decrypt sensitive fields in configuration.

        Args:
            config: Configuration dictionary with encrypted fields
            sensitive_fields: List of field names that should be decrypted

        Returns:
            Configuration dictionary with sensitive fields decrypted and renamed
            from 'encrypted_{field_name}' back to '{field_name}' format

        Example:
            >>> service = EncryptionService()
            >>> config = {"encrypted_api_key": "...", "timeout": 30}
            >>> decrypted = service.decrypt_sensitive_fields(config, ["api_key"])
            >>> # Result: {"api_key": "secret123", "timeout": 30}
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
                encrypted_field_value = decrypted_config[encrypted_field]
                decrypted_value = cipher.decrypt(
                    str(encrypted_field_value).encode()
                ).decode()
                decrypted_config[field] = decrypted_value
                del decrypted_config[encrypted_field]

        return decrypted_config
