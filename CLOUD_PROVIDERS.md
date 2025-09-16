# Adding a New Cloud Provider

This document outlines the steps required to add support for a new cloud provider to the Borgitory cloud sync system.

## Overview

The cloud sync system is designed with a modular architecture that makes adding new providers straightforward. Each provider consists of:

- **Storage Configuration Schema**: Defines and validates provider-specific settings
- **Storage Implementation**: Handles the actual upload/download operations
- **Frontend Templates**: Provides the user interface for configuration
- **Integration Points**: Connects the provider to the main system

Borgitory uses **[rclone](https://rclone.org/)** for syncing. Borgitory can theoretically support any destination that rclone does.

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
```

### 2. Update the Storage Factory

Edit `src/services/cloud_providers/service.py`:

```python
# Add import at the top
from .storage import (
    # ... existing imports ...
    {ProviderName}Storage,
    {ProviderName}StorageConfig,
)

class ConfigValidator:
    def validate_config(self, provider: str, config: Dict[str, Any]) -> Any:
        # Add your provider case
        if provider == "{provider_name}":
            return {ProviderName}StorageConfig(**config)
        # ... existing cases ...

class StorageFactory:
    def create_storage(self, provider: str, config: Dict[str, Any]) -> CloudStorage:
        # Add your provider case
        if provider == "{provider_name}":
            return {ProviderName}Storage(validated_config, self._rclone_service)
        # ... existing cases ...
```

### 3. Update the Storage Module Exports

Edit `src/services/cloud_providers/storage/__init__.py`:

```python
from .{provider_name}_storage import {ProviderName}Storage, {ProviderName}StorageConfig

__all__ = [
    # ... existing exports ...
    "{ProviderName}Storage",
    "{ProviderName}StorageConfig",
]
```

### 4. Update the Provider Enum

Edit `src/models/enums.py`:

```python
class ProviderType(str, Enum):
    # ... existing providers ...
    {PROVIDER_NAME_UPPER} = "{provider_name}"
```

### 5. Create Frontend Template

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

### 7. Update API Provider Fields Endpoint

Edit `src/api/cloud_sync.py` in the `get_provider_fields` function:

```python
@router.get("/provider-fields", response_class=HTMLResponse)
async def get_provider_fields(
    request: Request,
    provider: str = "",
    templates: Jinja2Templates = Depends(get_templates),
) -> HTMLResponse:
    """Get dynamic provider fields based on selection"""
    context = {
        "provider": provider,
        "is_s3": provider == "s3",
        "is_sftp": provider == "sftp",
        "is_{provider_name}": provider == "{provider_name}",  # Add this line
    }

    # Update submit button text
    if provider == "s3":
        context["submit_text"] = "Add S3 Location"
    elif provider == "sftp":
        context["submit_text"] = "Add SFTP Location"
    elif provider == "{provider_name}":  # Add this block
        context["submit_text"] = "Add {Provider Name} Location"
    elif provider == "":
        context["submit_text"] = "Add Sync Location"
        context["show_submit"] = False
    else:
        context["submit_text"] = "Add Sync Location"
        context["show_submit"] = True

    # Set show_submit flag
    context["show_submit"] = provider != ""

    return templates.TemplateResponse(
        request, "partials/cloud_sync/provider_fields.html", context
    )
```

### 8. Update Service Layer

Edit `src/services/cloud_sync_service.py` to add the provider to sensitive fields detection:

```python
def get_decrypted_config_for_editing(
    self, config_id: int, encryption_service, storage_factory
) -> dict:
    # ... existing code ...
    
    # Add your provider to the sensitive fields detection
    if config.provider == "s3":
        sensitive_fields = ["access_key", "secret_key"]
    elif config.provider == "sftp":
        sensitive_fields = ["password", "private_key"]
    elif config.provider == "{provider_name}":  # Add this
        sensitive_fields = ["api_key"]  # Add your sensitive fields
    else:
        sensitive_fields = []

async def test_cloud_sync_config(
    self,
    config_id: int,
    rclone: RcloneService,
    encryption_service=None,
    storage_factory=None,
) -> dict:
    # ... existing code ...
    
    # Add your provider to the sensitive fields detection (same as above)
    if config.provider == "s3":
        sensitive_fields = ["access_key", "secret_key"]
    elif config.provider == "sftp":
        sensitive_fields = ["password", "private_key"]
    elif config.provider == "{provider_name}":  # Add this
        sensitive_fields = ["api_key"]  # Add your sensitive fields
    else:
        sensitive_fields = []
```

### 9. Update Provider Registry

Edit the `SUPPORTED_PROVIDERS` list in `src/api/cloud_sync.py`:

```python
# Provider registry - single source of truth for supported providers
SUPPORTED_PROVIDERS = [
    {"value": "s3", "label": "AWS S3", "description": "Amazon S3 compatible storage"},
    {"value": "sftp", "label": "SFTP (SSH)", "description": "Secure File Transfer Protocol"},
    {"value": "{provider_name}", "label": "{Provider Display Name}", "description": "{Provider description}"},  # Add this line
]
```

The frontend dropdown will automatically pick up the new provider since it's built server-side from this list.

### 10. Implement Rclone Integration

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

### 11. Add Supported Providers List

Update `src/services/cloud_sync_service.py`:

```python
def create_cloud_sync_config(
    self, config: CloudSyncConfigCreate
) -> CloudSyncConfig:
    # Update supported providers list
    supported_providers = ["s3", "sftp", "{provider_name}"]  # Add your provider
    if config.provider.value not in supported_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {config.provider}. Available providers: {', '.join(supported_providers)}",
        )
```

### 12. Create Tests

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

1. **Run the validation tests**:
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

2. **Run the unit tests**:
   ```bash
   python -m pytest tests/cloud_providers/test_{provider_name}_storage.py -v
   ```

3. **Run integration tests**:
   ```bash
   python -m pytest tests/cloud_sync/ -v
   ```

4. **Test the frontend**:
   - Start the application
   - Navigate to Cloud Sync settings
   - Select your new provider from the dropdown
   - Verify the form fields appear correctly
   - Try creating a configuration (will fail without real credentials, but should show proper validation)

## Common Pitfalls

1. **Sensitive Fields**: Make sure to add all sensitive fields to `get_sensitive_fields()` and update the service layer detection
2. **Form Field Names**: Use bracket notation in templates: `provider_config[field_name]`
3. **Validation**: Add comprehensive validation in the config class - this is your first line of defense
4. **Error Handling**: Provide clear error messages in validation and connection testing
5. **Rclone Integration**: The rclone service methods need to match your provider's rclone backend capabilities
6. **Testing**: Create both unit tests for the storage classes and integration tests for the full flow

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

## Final Steps

1. Update this documentation with any provider-specific details
2. Add the provider to the main README.md supported providers list
3. Consider adding provider-specific documentation in the `docs/` folder
4. Update any deployment documentation if new dependencies are required
