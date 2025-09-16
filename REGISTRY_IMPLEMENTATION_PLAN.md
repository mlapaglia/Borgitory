# Registry Pattern Implementation Plan

## Overview
Implement a dynamic registry system for cloud providers to replace hardcoded if/elif chains in the service layer.

## Phase 1: Create Registry Infrastructure ✅ COMPLETED

### 1.1 Create Registry Module
- [x] **File**: `src/services/cloud_providers/registry.py`
- [x] **Purpose**: Central registry for provider configurations and storage classes
- [x] **Components**:
  - [x] `_CONFIG_REGISTRY` dictionary to store provider -> config class mappings
  - [x] `_STORAGE_REGISTRY` dictionary to store provider -> storage class mappings
  - [x] `@register_provider` decorator that registers both config and storage classes
  - [x] `get_config_class(provider)` function
  - [x] `get_storage_class(provider)` function
  - [x] `get_supported_providers()` function that returns list of registered providers

### 1.2 Registry Structure
```python
# Example structure
_REGISTRIES = {
    'config': {},    # provider -> config class
    'storage': {},   # provider -> storage class
    'metadata': {}   # provider -> metadata dict
}

@register_provider(
    name="s3",
    description="Amazon S3 compatible storage",
    metadata={"supports_encryption": True, "supports_versioning": True}
)
class S3Provider:
    config_class = S3StorageConfig
    storage_class = S3Storage
```

## Phase 2: Modify Existing Storage Classes ✅ COMPLETED

### 2.1 Update Storage Config Classes
- [x] **Files**: 
  - [x] `src/services/cloud_providers/storage/s3_storage.py`
  - [x] `src/services/cloud_providers/storage/sftp_storage.py`
  - [x] `src/services/cloud_providers/storage/smb_storage.py`
- [x] **Changes**:
  - [x] Add `@register_provider` decorator to each storage module
  - [x] Consider grouping config and storage classes together or keeping separate with cross-references

### 2.2 Update Storage Module Exports
- [x] **File**: `src/services/cloud_providers/storage/__init__.py`
- [x] **Changes**:
  - [x] Import registry module
  - [x] Ensure all storage modules are imported (to trigger registration)
  - [x] Consider adding `get_all_providers()` convenience function

## Phase 3: Refactor Service Layer ✅ COMPLETED

### 3.1 Update ConfigValidator
- [x] **File**: `src/services/cloud_providers/service.py`
- [x] **Changes**:
  - [x] Import registry functions
  - [x] Replace if/elif chain in `validate_config()` with registry lookup
  - [x] Add better error handling with available providers list
  - [x] Consider caching registry lookups for performance

### 3.2 Update StorageFactory
- [x] **File**: `src/services/cloud_providers/service.py`
- [x] **Changes**:
  - [x] Replace if/elif chain in `create_storage()` with registry lookup
  - [x] Use same registry for both validation and creation
  - [x] Add method to list supported providers

### 3.3 Update Cloud Sync Service
- [ ] **File**: `src/services/cloud_sync_service.py`
- [ ] **Changes**:
  - [ ] Replace hardcoded sensitive fields detection with registry-based approach
  - [ ] Use registry to get provider metadata instead of hardcoded lists

## Phase 4: Update API Layer

### 4.1 Dynamic Provider Registry
- [ ] **File**: `src/api/cloud_sync.py`
- [ ] **Changes**:
  - [ ] Replace `SUPPORTED_PROVIDERS` constant with registry-based function
  - [ ] Update `_get_supported_providers()` to use registry
  - [ ] Consider adding API endpoint to list available providers with metadata

### 4.2 Provider Validation
- [ ] **Files**: API validation logic
- [ ] **Changes**:
  - [ ] Use registry to validate provider names instead of hardcoded lists
  - [ ] Update error messages to include dynamically discovered providers

## Phase 5: Test Updates

### 5.1 Registry Tests
- [ ] **File**: `tests/cloud_providers/test_registry.py` (new)
- [ ] **Test Cases**:
  - [ ] Test provider registration and retrieval
  - [ ] Test duplicate provider registration handling
  - [ ] Test invalid provider lookup
  - [ ] Test metadata storage and retrieval
  - [ ] Test `get_supported_providers()` functionality

### 5.2 Update Existing Tests
- [ ] **Files**: 
  - [ ] `tests/cloud_providers/test_service.py`
  - [ ] `tests/cloud_providers/test_config_service.py`
  - [ ] All provider-specific test files
- [ ] **Changes**:
  - [ ] Update tests that rely on hardcoded provider lists
  - [ ] Test dynamic provider discovery
  - [ ] Add tests for registry-based validation
  - [ ] Mock registry for isolated testing

### 5.3 Integration Tests
- [ ] **File**: `tests/cloud_providers/test_integration.py` (new or existing)
- [ ] **Test Cases**:
  - [ ] Test that all registered providers work end-to-end
  - [ ] Test that registry is properly populated at startup
  - [ ] Test provider discovery across different modules

## Phase 6: Documentation Updates

### 6.1 Update CLOUD_PROVIDERS.md
- [ ] **Section**: "Step-by-Step Implementation Guide"
- [ ] **Changes**:
  - [ ] Add step for using `@register_provider` decorator
  - [ ] Update code examples to show registration pattern
  - [ ] Add section on provider metadata
  - [ ] Update testing examples to account for registry

### 6.2 Add Registry Documentation
- [ ] **Section**: New "Provider Registry System" section
- [ ] **Content**:
  - [ ] Explain how the registry works
  - [ ] Document decorator usage
  - [ ] Explain metadata system
  - [ ] Show how to query available providers

### 6.3 Update Common Pitfalls
- [ ] **Section**: "Common Pitfalls"
- [ ] **New Items**:
  - [ ] "Provider Registration": Remember to use `@register_provider` decorator
  - [ ] "Import Order": Ensure storage modules are imported to trigger registration
  - [ ] "Testing": Mock registry for isolated unit tests

## Phase 7: Migration and Backwards Compatibility

### 7.1 Gradual Migration Strategy
- [ ] **Phase 7.1**: Implement registry alongside existing if/elif chains
- [ ] **Phase 7.2**: Add feature flag to switch between old and new systems
- [ ] **Phase 7.3**: Update tests to work with both systems
- [ ] **Phase 7.4**: Remove old if/elif chains after thorough testing

### 7.2 Backwards Compatibility
- [ ] Ensure existing provider names continue to work
- [ ] Maintain same API contracts
- [ ] Consider deprecation warnings for any changed interfaces

## Implementation Timeline

1. **Week 1**: Phase 1 (Registry Infrastructure) + Phase 2 (Update Storage Classes)
2. **Week 2**: Phase 3 (Refactor Service Layer) + Phase 4 (Update API Layer)
3. **Week 3**: Phase 5 (Test Updates) + Phase 6 (Documentation)
4. **Week 4**: Phase 7 (Migration and Testing)

## Risk Mitigation

### Testing Strategy
- Implement registry alongside existing code initially
- Use feature flags to switch between implementations
- Comprehensive integration tests before removing old code
- Test all existing providers still work

### Rollback Plan
- Keep old if/elif implementation until new system is proven
- Use git feature branches for safe experimentation
- Monitor for any performance regressions

### Dependencies
- No new external dependencies required
- Uses only Python standard library features
- Compatible with existing pydantic validation

## Progress Tracking

- [x] Phase 1: Registry Infrastructure ✅ COMPLETED
- [x] Phase 2: Storage Classes Update ✅ COMPLETED  
- [x] Phase 3: Service Layer Refactor ✅ COMPLETED
- [x] Phase 4: API Layer Update ✅ COMPLETED
- [x] Phase 5: Test Updates ✅ COMPLETED
- [ ] Phase 6: Documentation (Optional)
- [ ] Phase 7: Migration & Cleanup (Not needed - implemented alongside existing code)

## Notes
- Start with Phase 1.1 - Create the registry module
- Keep existing functionality working throughout implementation
- Test thoroughly at each phase before proceeding
