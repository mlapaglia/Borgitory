# Hybrid DI Services Usage Analysis

## Services to Convert from Hybrid to Pure FastAPI DI

### 1. **BorgService**
- **Type Alias**: `BorgServiceDep` ✅ (exists)
- **API Usage**: `src/borgitory/api/repositories.py` (uses `BorgServiceDep`)
- **Test Usage**: `tests/test_dependencies.py` (4 direct calls)
- **Dependencies**: SimpleCommandRunner, VolumeService, JobManager
- **Risk Level**: HIGH (widely used in repositories API)

### 2. **DebugService** 
- **Type Alias**: `DebugServiceDep` ✅ (exists)
- **API Usage**: `src/borgitory/api/debug.py` (uses `DebugServiceDep`)
- **Test Usage**: `tests/test_dependencies.py` (3 direct calls)
- **Dependencies**: VolumeService, JobManager
- **Risk Level**: LOW (limited to debug API)

### 3. **JobStreamService**
- **Type Alias**: `JobStreamServiceDep` ✅ (exists)
- **API Usage**: `src/borgitory/api/jobs.py` (uses `JobStreamServiceDep`)
- **Test Usage**: `tests/test_dependencies.py` (2 direct calls), `tests/jobs/test_job_stream_service.py` (2 direct calls)
- **Dependencies**: JobManager
- **Risk Level**: MEDIUM (used in job streaming)

### 4. **JobRenderService**
- **Type Alias**: `JobRenderServiceDep` ✅ (exists)  
- **API Usage**: `src/borgitory/api/jobs.py` (uses `JobRenderServiceDep`)
- **Test Usage**: `tests/test_dependencies.py` (2 direct calls), `tests/jobs/test_job_render_service.py` (2 direct calls)
- **Dependencies**: JobManager
- **Risk Level**: MEDIUM (used in job rendering)

### 5. **ArchiveManager**
- **Type Alias**: `ArchiveManagerDep` ✅ (exists)
- **API Usage**: None found (may be used indirectly)
- **Test Usage**: None found with direct calls
- **Dependencies**: JobExecutor, BorgCommandBuilder
- **Risk Level**: LOW (least risky conversion)

### 6. **RepositoryService**
- **Type Alias**: `RepositoryServiceDep` ✅ (exists)
- **API Usage**: `src/borgitory/api/repositories.py` (uses `RepositoryServiceDep`)
- **Test Usage**: None found with direct calls
- **Dependencies**: BorgService, SchedulerService, VolumeService
- **Risk Level**: HIGH (depends on BorgService which is also being converted)

## Current DI Usage Patterns

### ✅ **Good News**: APIs Already Use Type Aliases
- All APIs are already using the `*Dep` type aliases
- This means the APIs are already prepared for pure FastAPI DI
- No API changes needed during conversion

### ⚠️ **Challenge Areas**: Direct Test Calls
- `tests/test_dependencies.py`: 11 direct calls to hybrid services
- `tests/jobs/test_job_stream_service.py`: 2 direct calls  
- `tests/jobs/test_job_render_service.py`: 2 direct calls
- These tests expect singleton behavior and will need updating

### 🔧 **Internal Dependencies**
- `get_repository_service()` calls `get_borg_service()` internally
- This creates a dependency chain that needs careful conversion order

## Conversion Priority (Safest First)

1. **ArchiveManager** - No direct usage found, simple dependencies
2. **DebugService** - Limited API usage, straightforward dependencies
3. **JobStreamService** - Single dependency (JobManager)
4. **JobRenderService** - Single dependency (JobManager)  
5. **BorgService** - Complex but no internal dependencies on other hybrid services
6. **RepositoryService** - Must be last (depends on BorgService)

## Test Update Strategy

### Current Test Pattern (Hybrid):
```python
def test_service():
    service = get_borg_service()  # Direct call
    assert service is not None
```

### Target Test Pattern (Pure DI):
```python
def test_service():
    from fastapi.testclient import TestClient
    from borgitory.main import app
    
    mock_service = Mock(spec=BorgService)
    
    with TestClient(app) as client:
        app.dependency_overrides[get_borg_service] = lambda: mock_service
        # Test via API endpoints or dependency injection context
        app.dependency_overrides.clear()
```

## Risk Mitigation

### Low Risk:
- ArchiveManager, DebugService (limited usage)

### Medium Risk: 
- JobStreamService, JobRenderService (moderate test updates needed)

### High Risk:
- BorgService, RepositoryService (widely used, complex dependencies)

## Next Steps

1. Create dependency override testing infrastructure
2. Create regression tests for current behavior  
3. Convert services in priority order
4. Update tests to use dependency overrides
5. Validate no functional changes
