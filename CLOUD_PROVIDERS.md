# Adding a New Cloud Provider

This document outlines the steps required to add support for a new cloud provider to the Borgitory cloud sync system.

## Overview

The cloud sync system is designed with a modular architecture that makes adding new providers straightforward. Each provider consists of:

- **Storage Configuration Schema**: Defines and validates provider-specific settings
- **Storage Implementation**: Handles the actual upload/download operations
- **Frontend Templates**: Provides the user interface for configuration
- **Integration Points**: Connects the provider to the main system

Borgitory uses **[rclone](https://rclone.org/)** for syncing. Borgitory can theoretically support any destination that rclone does.

## Registry Pattern

Borgitory uses a **registry pattern** for cloud providers, which means:

- **No hardcoded provider lists**: Providers are automatically discovered
- **Dynamic registration**: Use the `@register_provider` decorator to register your provider
- **Automatic integration**: Once registered, your provider appears in APIs, validation, and frontend dropdowns
- **Metadata support**: Include provider capabilities like versioning support, encryption, etc.

This eliminates the need to manually update multiple files when adding a provider!

## Step-by-Step Implementation Guide

### 1. Create the Storage Configuration Schema

Create a new file: `src/services/cloud_providers/storage/{provider_name}_storage.py`

```python
"""
{Provider Name} cloud storage implementation.
"""

from typing import Callable, Optional
from pydantic import Field, field_validator, model_validator

from .base import CloudStorage, CloudStorageConfig
from ..types import SyncEvent, SyncEventType, ConnectionInfo
from ..registry import register_provider


class {ProviderName}StorageConfig(CloudStorageConfig):
    """Configuration for {Provider Name} storage"""

    # Define your provider-specific fields here
    # Example fields (customize based on your provider):
    endpoint_url: str = Field(..., min_length=1, description="Provider endpoint URL")
    api_key: str = Field(..., min_length=1, description="API key for authentication")
    bucket_name: str = Field(..., min_length=1, max_length=255, description="Bucket/container name")
    region: Optional[str] = Field(default=None, description="Region (if applicable)")

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, v: str) -> str:
        """Validate endpoint URL format"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Endpoint URL must start with http:// or https://")
        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format"""
        # Add your specific validation logic here
        if len(v) < 10:  # Example validation
            raise ValueError("API key must be at least 10 characters long")
        return v

    @field_validator("bucket_name")
    @classmethod
    def validate_bucket_name(cls, v: str) -> str:
        """Validate bucket name format"""
        # Add provider-specific bucket naming rules
        import re
        if not re.match(r'^[a-zA-Z0-9\-_]+$', v):
            raise ValueError("Bucket name can only contain letters, numbers, hyphens, and underscores")
        return v.lower()

    # Add model validator for complex validation if needed
    @model_validator(mode="after")
    def validate_config_combination(self):
        """Validate field combinations if needed"""
        # Example: certain fields might be mutually exclusive
        # or required together
        return self


class {ProviderName}Storage(CloudStorage):
    """
    {Provider Name} cloud storage implementation.
    """

    def __init__(self, config: {ProviderName}StorageConfig, rclone_service):
        """
        Initialize {Provider Name} storage.

        Args:
            config: Validated {Provider Name} configuration
            rclone_service: Injected rclone service for I/O operations
        """
        self._config = config
        self._rclone_service = rclone_service

    async def upload_repository(
        self,
        repository_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[SyncEvent], None]] = None,
    ) -> None:
        """Upload repository to {Provider Name}"""
        if progress_callback:
            progress_callback(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting {Provider Name} upload to {self._config.bucket_name}",
                )
            )

        try:
            # Implement your upload logic here using rclone_service
            # Example structure:
            await self._rclone_service.upload_to_{provider_name}(
                source_path=repository_path,
                remote_path=remote_path,
                endpoint_url=self._config.endpoint_url,
                api_key=self._config.api_key,
                bucket_name=self._config.bucket_name,
                region=self._config.region,
                progress_callback=progress_callback,
            )

            if progress_callback:
                progress_callback(
                    SyncEvent(
                        type=SyncEventType.COMPLETED,
                        message=f"Successfully uploaded to {Provider Name}",
                    )
                )

        except Exception as e:
            error_msg = f"Failed to upload to {Provider Name}: {str(e)}"
            if progress_callback:
                progress_callback(
                    SyncEvent(
                        type=SyncEventType.ERROR,
                        message=error_msg,
                    )
                )
            raise Exception(error_msg) from e

    async def test_connection(self) -> bool:
        """Test {Provider Name} connection"""
        try:
            result = await self._rclone_service.test_{provider_name}_connection(
                endpoint_url=self._config.endpoint_url,
                api_key=self._config.api_key,
                bucket_name=self._config.bucket_name,
                region=self._config.region,
            )
            return result.get("status") == "success"
        except Exception:
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get {Provider Name} connection info for display"""
        return ConnectionInfo(
            provider="{provider_name}",
            details={
                "endpoint": self._config.endpoint_url,
                "bucket": self._config.bucket_name,
                "region": self._config.region or "default",
                "api_key": f"{self._config.api_key[:4]}***{self._config.api_key[-4:]}"
                if len(self._config.api_key) > 8
                else "***",
            },
        )

    def get_sensitive_fields(self) -> list[str]:
        """{Provider Name} sensitive fields that should be encrypted"""
        return ["api_key"]  # Add all sensitive field names here

    def get_display_details(self, config_dict: dict) -> dict:
        """Get {Provider Name}-specific display details for the UI"""
        endpoint = config_dict.get("endpoint_url", "Unknown")
        bucket = config_dict.get("bucket_name", "Unknown")
        region = config_dict.get("region", "default")
        
        provider_details = f"""
            <div><strong>Endpoint:</strong> {endpoint}</div>
            <div><strong>Bucket:</strong> {bucket}</div>
            <div><strong>Region:</strong> {region}</div>
        """.strip()
        
        return {
            "provider_name": "{Provider Display Name}",
            "provider_details": provider_details
        }


@register_provider(
    name="{provider_name}",
    label="{Provider Display Name}",
    description="{Provider description}",
    supports_encryption=True,
    supports_versioning=False,  # Set to True if your provider supports versioning
    requires_credentials=True
)
class {ProviderName}Provider:
    """{Provider Name} provider registration"""
    config_class = {ProviderName}StorageConfig
    storage_class = {ProviderName}Storage
```

### 2. Update the Storage Module Exports

Edit `src/services/cloud_providers/storage/__init__.py`:

```python
from .{provider_name}_storage import {ProviderName}Storage, {ProviderName}StorageConfig

__all__ = [
    # ... existing exports ...
    "{ProviderName}Storage",
    "{ProviderName}StorageConfig",
]
```

### 3. Create Frontend Template

Create `src/templates/partials/cloud_sync/providers/{provider_name}_fields.html`:

```html
<!-- {Provider Name} Fields -->
<div id="{provider_name}-fields">
    <div>
        <label class="block text-sm font-medium text-gray-900 dark:text-gray-100">Endpoint URL</label>
        <input type="text" name="provider_config[endpoint_url]" placeholder="https://api.{provider}.com" class="input-modern mt-1">
    </div>
    <div>
        <label class="block text-sm font-medium text-gray-900 dark:text-gray-100">API Key</label>
        <input type="password" name="provider_config[api_key]" class="input-modern mt-1">
    </div>
    <div>
        <label class="block text-sm font-medium text-gray-900 dark:text-gray-100">Bucket Name</label>
        <input type="text" name="provider_config[bucket_name]" placeholder="my-backup-bucket" class="input-modern mt-1">
    </div>
    <div>
        <label class="block text-sm font-medium text-gray-900 dark:text-gray-100">Region (optional)</label>
        <input type="text" name="provider_config[region]" placeholder="us-east-1" class="input-modern mt-1">
    </div>
    <div>
        <label class="block text-sm font-medium text-gray-900 dark:text-gray-100">Path Prefix (optional)</label>
        <input type="text" name="path_prefix" placeholder="backups/borgitory" class="input-modern mt-1">
    </div>
</div>
```

### 4. Update Frontend Template Context

Edit `src/api/cloud_sync.py` in the `get_provider_fields` function to add your provider's context variable:

```python
context = {
    "provider": provider,
    "is_s3": provider == "s3",
    "is_sftp": provider == "sftp",
    "is_smb": provider == "smb",
    "is_{provider_name}": provider == "{provider_name}",  # Add this line for template logic
}
```

**Note**: With the registry pattern, submit button text and provider validation are handled automatically. You only need to add the `is_{provider_name}` context variable for template conditional logic.

## What's No Longer Needed ✨

Thanks to the registry pattern, you **do not** need to:

- ❌ **Update Provider Enums**: No more manual enum updates in `src/models/schemas.py`
- ❌ **Update Service Layer**: No hardcoded if/elif chains in service classes
- ❌ **Update API Provider Lists**: No manual provider lists in `src/api/cloud_sync.py`
- ❌ **Update Sensitive Field Detection**: Handled automatically via registry
- ❌ **Update Submit Button Logic**: Generated automatically from registry metadata

The `@register_provider` decorator handles all of this automatically!

### 5. Implement Rclone Integration

Add methods to `src/services/rclone_service.py`:

```python
async def test_{provider_name}_connection(
    self,
    endpoint_url: str,
    api_key: str,
    bucket_name: str,
    region: Optional[str] = None,
) -> dict:
    """Test {Provider Name} connection"""
    try:
        # Implement your connection test logic
        # This will vary based on your provider's API
        pass
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def upload_to_{provider_name}(
    self,
    source_path: str,
    remote_path: str,
    endpoint_url: str,
    api_key: str,
    bucket_name: str,
    region: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> None:
    """Upload to {Provider Name} using rclone"""
    try:
        # Implement your upload logic using rclone
        # This will vary based on your provider's rclone backend
        pass
    except Exception as e:
        raise Exception(f"Failed to upload to {Provider Name}: {str(e)}") from e
```

### 6. Create Tests

Create `tests/cloud_providers/test_{provider_name}_storage.py`:

```python
import pytest
from unittest.mock import Mock, AsyncMock
from src.services.cloud_providers.storage.{provider_name}_storage import (
    {ProviderName}StorageConfig,
    {ProviderName}Storage,
)


class Test{ProviderName}StorageConfig:
    """Test {Provider Name} storage configuration validation"""

    def test_valid_config(self):
        """Test valid configuration passes validation"""
        config = {ProviderName}StorageConfig(
            endpoint_url="https://api.{provider}.com",
            api_key="valid-api-key-12345",
            bucket_name="test-bucket",
            region="us-east-1",
        )
        assert config.endpoint_url == "https://api.{provider}.com"
        assert config.bucket_name == "test-bucket"

    def test_invalid_endpoint_url(self):
        """Test invalid endpoint URL raises validation error"""
        with pytest.raises(ValueError, match="Endpoint URL must start with"):
            {ProviderName}StorageConfig(
                endpoint_url="invalid-url",
                api_key="valid-api-key-12345",
                bucket_name="test-bucket",
            )

    def test_invalid_api_key(self):
        """Test invalid API key raises validation error"""
        with pytest.raises(ValueError, match="API key must be at least"):
            {ProviderName}StorageConfig(
                endpoint_url="https://api.{provider}.com",
                api_key="short",
                bucket_name="test-bucket",
            )


class Test{ProviderName}Storage:
    """Test {Provider Name} storage implementation"""

    @pytest.fixture
    def mock_rclone_service(self):
        return AsyncMock()

    @pytest.fixture
    def storage_config(self):
        return {ProviderName}StorageConfig(
            endpoint_url="https://api.{provider}.com",
            api_key="valid-api-key-12345",
            bucket_name="test-bucket",
            region="us-east-1",
        )

    @pytest.fixture
    def storage(self, storage_config, mock_rclone_service):
        return {ProviderName}Storage(storage_config, mock_rclone_service)

    @pytest.mark.asyncio
    async def test_test_connection_success(self, storage, mock_rclone_service):
        """Test successful connection test"""
        mock_rclone_service.test_{provider_name}_connection.return_value = {
            "status": "success"
        }
        
        result = await storage.test_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, storage, mock_rclone_service):
        """Test failed connection test"""
        mock_rclone_service.test_{provider_name}_connection.side_effect = Exception("Connection failed")
        
        result = await storage.test_connection()
        assert result is False

    def test_get_sensitive_fields(self, storage):
        """Test sensitive fields are correctly identified"""
        sensitive_fields = storage.get_sensitive_fields()
        assert "api_key" in sensitive_fields

    def test_get_connection_info(self, storage):
        """Test connection info formatting"""
        info = storage.get_connection_info()
        assert info.provider == "{provider_name}"
        assert "api_key" in info.details
        assert "***" in info.details["api_key"]  # Should be masked
```

Add tests to the service layer in `tests/cloud_sync/test_cloud_sync_service.py`:

```python
def test_create_{provider_name}_config_success(self, service, test_db):
    """Test successful {Provider Name} config creation."""
    config_data = CloudSyncConfigCreate(
        name="test-{provider_name}",
        provider="{provider_name}",
        provider_config={
            "endpoint_url": "https://api.{provider}.com",
            "api_key": "valid-api-key-12345",
            "bucket_name": "test-bucket",
            "region": "us-east-1",
        },
        path_prefix="backups/",
    )

    result = service.create_cloud_sync_config(config_data)

    # Verify the result
    assert result.name == "test-{provider_name}"
    assert result.provider == "{provider_name}"
    assert result.path_prefix == "backups/"
```

## Testing Your Implementation

### 1. Configuration Validation Tests

```bash
python -c "
from src.services.cloud_providers.storage.{provider_name}_storage import {ProviderName}StorageConfig
config = {ProviderName}StorageConfig(
    endpoint_url='https://api.{provider}.com',
    api_key='valid-api-key-12345',
    bucket_name='test-bucket'
)
print('Configuration validation passed!')
"
```

### 2. Unit Tests

```bash
python -m pytest tests/cloud_providers/test_{provider_name}_storage.py -v
```

### 3. Integration Tests

```bash
python -m pytest tests/cloud_sync/ -v
```

### 4. Full Cloud Provider Test Suite

```bash
python -m pytest tests/cloud_providers/ -v
```

### 5. Registry Integration Test

Verify your provider is automatically registered:

```bash
python -c "
import sys; sys.path.append('src')
from services.cloud_providers.registry import get_supported_providers, get_all_provider_info

# Import your storage module to trigger registration
import services.cloud_providers.storage.{provider_name}_storage

print('Registered providers:', get_supported_providers())
info = get_all_provider_info()
if '{provider_name}' in info:
    print('✅ {Provider Name} successfully registered!')
    print('Metadata:', info['{provider_name}'])
else:
    print('❌ {Provider Name} not found in registry')
"
```

### 6. Frontend Testing

- Start the application
- Navigate to Cloud Sync settings
- Your provider should automatically appear in the dropdown (thanks to the registry!)
- Select your provider and verify the form fields appear correctly
- Try creating a configuration (will fail without real credentials, but should show proper validation)

## Testing Best Practices

### Pydantic Field Aliases in Tests

When your configuration uses field aliases (common for reserved keywords), ensure tests use the correct format:

```python
# ❌ Wrong - will cause validation errors
config = ProviderStorageConfig(
    host="example.com",
    reserved_field="value"  # This won't work with aliases
)

# ✅ Correct - use alias with kwargs unpacking
config = ProviderStorageConfig(
    host="example.com",
    **{"reserved-field": "value"}  # Use the alias name
)
```

### Mocking Async Generators

Rclone service methods return async generators. Mock them properly:

```python
# ❌ Wrong - will cause parameter errors
async def mock_sync_generator():
    yield {"type": "completed"}

# ✅ Correct - accept all parameters
async def mock_sync_generator(*args, **kwargs):
    yield {"type": "completed"}

mock_rclone_service.sync_repository_to_provider = mock_sync_generator
```

### Duration Field Testing

Test various duration formats if your provider supports timeout configurations:

```python
def test_valid_duration_formats(self):
    """Test various valid duration formats"""
    valid_durations = ["30s", "1m", "1m30s", "2h", "1h30m", "1h30m45s"]
    for duration in valid_durations:
        config = ProviderStorageConfig(
            host="example.com",
            timeout=duration,
        )
        assert config.timeout == duration
```

## Common Pitfalls

1. **Sensitive Fields**: Make sure to add all sensitive fields to `get_sensitive_fields()` and update the service layer detection
2. **Form Field Names**: Use bracket notation in templates: `provider_config[field_name]`
3. **Validation**: Add comprehensive validation in the config class - this is your first line of defense
4. **Error Handling**: Provide clear error messages in validation and connection testing
5. **Rclone Integration**: The rclone service methods need to match your provider's rclone backend capabilities
6. **Testing**: Create both unit tests for the storage classes and integration tests for the full flow
7. **Pydantic Field Aliases**: When using field aliases (e.g., `pass_` with `alias="pass"`), tests must use the alias name with kwargs unpacking: `**{"pass": "value"}` instead of `pass_="value"`
8. **Async Generator Mocking**: For rclone service methods that return `AsyncGenerator[Dict, None]`, test mocks need to accept variable arguments: `async def mock_generator(*args, **kwargs):`
9. **Duration Field Validation**: When validating duration strings (like timeouts), use specific regex patterns that match the expected format (e.g., `^\d+[smh](\d+[smh])*$` for "1m30s" format)
10. **Connection Testing**: Implement comprehensive connection testing including read/write permissions, not just basic connectivity

## Provider-Specific Considerations

### For Object Storage Providers (S3-like)

- Follow S3 patterns for bucket naming, regions, storage classes
- Consider implementing storage class options if supported
- Add endpoint URL validation for custom S3-compatible services

### For File Transfer Providers (SFTP-like)

- Focus on connection authentication (keys, passwords, certificates)
- Validate host/port combinations
- Consider connection timeout and retry logic

### For API-based Providers

- Implement proper API key validation and formatting
- Add rate limiting considerations
- Handle API versioning if applicable

## Advanced Implementation Patterns

### Field Validation Patterns

When implementing field validation, consider these common patterns:

#### Host/Domain Validation

```python
@field_validator("host")
@classmethod
def validate_host(cls, v: str) -> str:
    """Validate host format"""
    import re
    
    # Basic validation for hostname or IP
    if not re.match(r"^[a-zA-Z0-9.-]+$", v):
        raise ValueError(
            "Host must contain only letters, numbers, periods, and hyphens"
        )
    if v.startswith(".") or v.endswith("."):
        raise ValueError("Host cannot start or end with a period")
    if ".." in v:
        raise ValueError("Host cannot contain consecutive periods")
    return v.lower()
```

#### Duration Field Validation

```python
@field_validator("timeout")
@classmethod
def validate_timeout(cls, v: str) -> str:
    """Validate timeout duration format"""
    import re
    
    # Validate duration format like "1m0s", "30s", "2h", etc.
    if not re.match(r"^\d+[smh](\d+[smh])*$", v):
        raise ValueError(
            "Timeout must be in duration format (e.g., '1m0s', '30s', '2h')"
        )
    return v
```

#### Username/Identifier Validation

```python
@field_validator("username")
@classmethod
def validate_username(cls, v: str) -> str:
    """Validate username format"""
    import re
    
    if not re.match(r"^[a-zA-Z0-9._-]+$", v):
        raise ValueError(
            "Username must contain only letters, numbers, periods, underscores, and hyphens"
        )
    return v
```

#### Complex Field Combinations

```python
@model_validator(mode="after")
def validate_auth_combination(self):
    """Validate authentication method combinations"""
    if self.use_oauth and self.api_key:
        raise ValueError("Cannot use both OAuth and API key authentication")
    
    if not self.use_oauth and not self.api_key:
        raise ValueError("Either OAuth or API key authentication must be configured")
    
    return self
```

### Reserved Keyword Handling

When your provider uses reserved Python keywords as field names, use aliases:

```python
class ProviderStorageConfig(CloudStorageConfig):
    # Use alias for reserved keywords
    pass_: Optional[str] = Field(default=None, alias="pass", description="Password")
    class_: Optional[str] = Field(default=None, alias="class", description="Storage class")
    
    # Remember to update sensitive fields to use the field name, not alias
    def get_sensitive_fields(self) -> list[str]:
        return ["pass_"]  # Use field name, not alias
```

## Final Steps

1. **That's it!** 🎉 With the registry pattern, your provider is automatically:
   - Available in API endpoints (`/api/cloud-sync/providers`)
   - Included in validation and error messages
   - Visible in frontend dropdowns
   - Integrated with the service layer

2. Update this documentation with any provider-specific details
3. Add the provider to the main README.md supported providers list
4. Consider adding provider-specific documentation in the `docs/` folder
5. Update any deployment documentation if new dependencies are required

## Registry Pattern Benefits

The registry pattern provides these key advantages:

### ✅ **Automatic Integration**

- Your provider appears in API endpoints (`/api/cloud-sync/providers`) automatically
- Frontend dropdowns populate without manual updates
- Validation includes your provider without code changes

### ✅ **Zero Boilerplate**

- No hardcoded if/elif chains in service classes
- No manual provider lists to maintain
- No enum updates required

### ✅ **Dynamic Capabilities**

- Provider metadata (encryption support, versioning, etc.) drives UI behavior
- Error messages automatically include your provider in "supported providers" lists
- Submit button text generated from registry metadata

### ✅ **Type Safety**

- Pydantic validators use registry for provider validation
- Comprehensive error messages with available providers
- Runtime provider discovery with compile-time safety

### ✅ **Developer Experience**

- Add one decorator, get full integration
- Consistent patterns across all providers
- Self-documenting through metadata

**Before Registry Pattern:**

```text
1. Create storage classes ✏️
2. Update provider enum ✏️
3. Update service layer ✏️
4. Update API endpoints ✏️
5. Update validation logic ✏️
6. Update frontend templates ✏️
7. Update sensitive field detection ✏️
```

**With Registry Pattern:**

```text
1. Create storage classes ✏️
2. Add @register_provider decorator ✨
3. Update frontend template ✏️
```

That's it! 🎉
