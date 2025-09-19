# Plan: Convert Remaining Hybrid Services to Pure FastAPI DI

## Overview
With tests being deleted and rewritten, we can now convert the remaining hybrid services (DebugService, BorgService, RepositoryService) to pure FastAPI DI. The only blocker was direct calls in tests - with those removed, we only have 1 direct call in `src/` to handle.

## Current State Analysis

### ✅ Already Using Pure FastAPI DI
- ArchiveManager ✅
- JobRenderService ✅ 
- JobStreamService ✅

### 🔄 Currently Hybrid (To Convert)
- DebugService (used in API via `DebugServiceDep`)
- BorgService (used in API via `BorgServiceDep`) 
- RepositoryService (used in API via `RepositoryServiceDep`)

### 📊 Direct Call Analysis in src/
**Only 1 direct call found**: `get_borg_service()` called inside `get_repository_service()`

```python
# Current hybrid pattern in dependencies.py
def get_repository_service() -> RepositoryService:
    return RepositoryService(
        borg_service=get_borg_service(),        # ← Only direct call in src/
        scheduler_service=get_scheduler_service(),
        volume_service=get_volume_service(),
    )
```

## Conversion Plan

### Phase 1: Convert DebugService (Easiest)
**No direct calls in src/ - only used via DI in APIs**

**Current:**
```python
@lru_cache()
def get_debug_service() -> DebugService:
    return DebugService(
        volume_service=get_volume_service(), 
        job_manager=get_job_manager_dependency()
    )
```

**Target:**
```python
def get_debug_service(
    volume_service: VolumeService = Depends(get_volume_service),
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> DebugService:
    return DebugService(
        volume_service=volume_service, 
        job_manager=job_manager
    )
```

**Impact:** Zero breaking changes - APIs already use `DebugServiceDep`

---

### Phase 2: Convert BorgService (Medium)
**1 direct call in src/ - used by RepositoryService**

**Current:**
```python
@lru_cache()
def get_borg_service() -> BorgService:
    return BorgService(
        command_runner=get_simple_command_runner(),
        volume_service=get_volume_service(),
        job_manager=get_job_manager_dependency(),
    )
```

**Target:**
```python
def get_borg_service(
    command_runner: SimpleCommandRunner = Depends(get_simple_command_runner),
    volume_service: VolumeService = Depends(get_volume_service),
    job_manager: JobManager = Depends(get_job_manager_dependency),
) -> BorgService:
    return BorgService(
        command_runner=command_runner,
        volume_service=volume_service,
        job_manager=job_manager,
    )
```

**Impact:** APIs continue to work (use `BorgServiceDep`), but need to fix RepositoryService

---

### Phase 3: Convert RepositoryService (Dependent on BorgService)
**Must be done AFTER BorgService conversion**

**Current:**
```python
@lru_cache()
def get_repository_service() -> RepositoryService:
    return RepositoryService(
        borg_service=get_borg_service(),           # ← Direct call to fix
        scheduler_service=get_scheduler_service(),
        volume_service=get_volume_service(),
    )
```

**Target:**
```python
def get_repository_service(
    borg_service: BorgService = Depends(get_borg_service),
    scheduler_service: ScheduleService = Depends(get_scheduler_service),
    volume_service: VolumeService = Depends(get_volume_service),
) -> RepositoryService:
    return RepositoryService(
        borg_service=borg_service,
        scheduler_service=scheduler_service,
        volume_service=volume_service,
    )
```

**Impact:** Zero breaking changes - APIs already use `RepositoryServiceDep`

---

## Implementation Steps

### Step 1: Convert DebugService
1. ✅ Convert `get_debug_service()` to pure FastAPI DI
2. ✅ Test API endpoints still work (`/api/debug/info`, `/api/debug/html`)
3. ✅ Verify `DebugServiceDep` type alias continues to work

### Step 2: Convert BorgService  
1. ✅ Convert `get_borg_service()` to pure FastAPI DI
2. ✅ Test API endpoints still work (repositories endpoints)
3. ✅ Verify `BorgServiceDep` type alias continues to work
4. ⚠️ **RepositoryService will be broken** until Step 3

### Step 3: Convert RepositoryService
1. ✅ Convert `get_repository_service()` to pure FastAPI DI
2. ✅ Test API endpoints still work (all repository endpoints)
3. ✅ Verify `RepositoryServiceDep` type alias continues to work

### Step 4: Rewrite Tests
1. ✅ Delete all existing tests that use direct calls
2. ✅ Rewrite tests to use `app.dependency_overrides` pattern
3. ✅ Use `tests/utils/di_testing.py` infrastructure
4. ✅ Test all services in FastAPI context only

## Expected Benefits

### 🎯 Pure FastAPI DI Architecture
- **All services** use pure FastAPI DI
- **No hybrid patterns** - consistent architecture
- **Better performance** - no `@lru_cache()` overhead
- **Request-scoped instances** - better resource management

### 🧪 Better Testing
- **Proper DI testing** via `dependency_overrides`
- **No direct calls** - tests only use FastAPI context
- **Better mocking** - services can be completely replaced
- **More realistic tests** - same DI path as production

### 🔧 Cleaner Code
- **Consistent patterns** across all services
- **No backward compatibility complexity**
- **Clear separation** between DI and business logic
- **Easier maintenance** - one DI pattern to understand

## Validation Checklist

### ✅ All API Endpoints Work
- `/api/debug/*` (DebugService)
- `/api/repositories/*` (BorgService, RepositoryService)
- All other endpoints continue to work

### ✅ Type Aliases Continue Working
- `DebugServiceDep` ✅
- `BorgServiceDep` ✅
- `RepositoryServiceDep` ✅

### ✅ No Direct Calls Remain
- Zero direct calls in `src/`
- All tests use dependency overrides
- Services only created via FastAPI DI

### ✅ Dependency Resolution Works
- All services receive actual instances (not `Depends` objects)
- Dependency chains resolve correctly
- No circular dependency issues

## Risk Assessment

### 🟢 Low Risk
- **API compatibility** maintained via type aliases
- **Gradual conversion** - one service at a time
- **Existing DI infrastructure** already in place

### 🟡 Medium Risk
- **RepositoryService temporarily broken** during BorgService conversion
- **Need to convert in correct order** (dependencies first)

### 🔴 Mitigation Strategies
- **Test after each conversion** - don't batch changes
- **Rollback plan** - keep git commits granular
- **API testing** - verify endpoints after each change

## Timeline

**Estimated: 2-3 hours**
- Step 1 (DebugService): 30 minutes
- Step 2 (BorgService): 45 minutes  
- Step 3 (RepositoryService): 45 minutes
- Step 4 (Test Rewrite): 60 minutes

**Total: All services converted to pure FastAPI DI** 🎉
