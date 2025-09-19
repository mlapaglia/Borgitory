# Type Ignore Elimination Plan

## Overview
We currently have 9 `# type: ignore` comments that were added as temporary fixes. This plan outlines how to properly resolve each one by fixing the underlying type issues.

## Current Type Ignores Analysis

### 1. **Any Return Issues** (3 instances)
**Files:** `job_manager.py`, `job_stream_service.py`
**Problem:** Functions declared to return concrete types but returning `Any` from dependencies

#### Issue 1: `job_manager.py:338` - `safe_executor`
```python
def safe_executor(self) -> JobExecutor:
    return self.executor  # type: ignore[no-any-return]
```
**Root Cause:** `self.executor` is typed as `Optional[Any]` in `JobManagerDependencies`
**Fix Strategy:** Update `JobManagerDependencies.job_executor` to use proper protocol type

#### Issue 2: `job_manager.py:1357` - Notification success
```python
return success  # type: ignore[no-any-return]
```
**Root Cause:** `success` comes from `Any` typed pushover_service
**Fix Strategy:** Update `JobManagerDependencies.pushover_service` to use `NotificationServiceProtocol`

#### Issue 3: `job_stream_service.py:386` - `get_job_status`
```python
return output  # type: ignore[no-any-return]
```
**Root Cause:** `get_job_output_stream` returns `Any` instead of proper type
**Fix Strategy:** Update `JobManagerProtocol.get_job_output_stream` return type

### 2. **Factory Type Issues** (4 instances)
**File:** `service_factory.py`
**Problem:** Generic factory system type mismatches

#### Issue 4-7: Factory convenience methods
```python
return self.get_factory("notifications")  # type: ignore[return-value]
```
**Root Cause:** `get_factory()` returns `ServiceFactory[Any]` but methods expect specific factory types
**Fix Strategy:** Implement proper generic factory registry with type-safe getters

### 3. **Protocol Compliance Issues** (2 instances)
**Files:** `service_factory.py`, `api/jobs.py`

#### Issue 8: BorgService protocol compliance
```python
return BorgService(  # type: ignore[return-value]
```
**Root Cause:** `BorgService` doesn't fully implement `BackupServiceProtocol`
**Fix Strategy:** Fix `BorgService.verify_repository_access` method signature to match protocol

#### Issue 9: Job manager dependency
```python
return get_jm_dep()  # type: ignore[return-value]
```
**Root Cause:** Function expects `JobManager` but gets `JobManagerProtocol`
**Fix Strategy:** Update function signature to accept protocol type

## Implementation Plan

### Phase 1: Fix Dependency Type Annotations
**Priority:** High
**Impact:** Fixes 3 Any-return issues
**Effort:** Medium

1. **Update JobManagerDependencies**
   - Change `job_executor: Optional[Any]` → `job_executor: Optional[ProcessExecutorProtocol]`
   - Change `pushover_service: Optional[Any]` → `pushover_service: Optional[NotificationServiceProtocol]`
   - Update all construction sites to handle protocol types

2. **Update JobManagerProtocol**
   - Fix `get_job_output_stream` return type from `Any` → `Dict[str, Any]`
   - Ensure all protocol methods have proper return types

### Phase 2: Fix Protocol Implementation Mismatches
**Priority:** High
**Impact:** Fixes 1 protocol compliance issue
**Effort:** Low

1. **Fix BorgService.verify_repository_access**
   - Current: `verify_repository_access(repo_path: str, passphrase: str, keyfile_path: str) -> bool`
   - Protocol expects: `verify_repository_access(repository: Any) -> Dict[str, Any]`
   - **Decision:** Update protocol to match BorgService implementation (more accurate)

### Phase 3: Implement Type-Safe Factory System
**Priority:** Medium
**Impact:** Fixes 4 factory type issues
**Effort:** High

1. **Create Specialized Factory Registry**
   ```python
   class TypedServiceRegistry:
       def __init__(self):
           self._notification_factory: NotificationServiceFactory = NotificationServiceFactory()
           self._command_runner_factory: CommandRunnerFactory = CommandRunnerFactory()
           self._backup_service_factory: BackupServiceFactory = BackupServiceFactory()
       
       def get_notification_factory(self) -> NotificationServiceFactory:
           return self._notification_factory
   ```

2. **Alternative: Use TypeVar with Literal types**
   ```python
   @overload
   def get_factory(self, name: Literal["notifications"]) -> NotificationServiceFactory: ...
   @overload
   def get_factory(self, name: Literal["command_runners"]) -> CommandRunnerFactory: ...
   ```

### Phase 4: Update API Dependencies
**Priority:** Low
**Impact:** Fixes 1 API dependency issue
**Effort:** Low

1. **Update jobs.py dependency**
   - Change `get_job_manager_dependency() -> JobManager` 
   - To: `get_job_manager_dependency() -> JobManagerProtocol`

## Testing Strategy

### For Each Phase:
1. **Run mypy** after each change to ensure no new errors
2. **Run protocol compliance tests** to ensure implementations still match
3. **Run full test suite** to ensure no functional regressions

### Validation Checklist:
- [ ] All `# type: ignore` comments removed
- [ ] `mypy src/borgitory --ignore-missing-imports` passes with 0 errors
- [ ] All protocol compliance tests pass
- [ ] Full test suite passes (1734+ tests)
- [ ] No new type ignores introduced

## Risk Assessment

### Low Risk:
- Phase 4 (API dependencies) - Simple signature change
- Phase 2 (Protocol fixes) - Just updating protocol definitions

### Medium Risk:
- Phase 1 (Dependency types) - Changes core JobManager behavior

### High Risk:
- Phase 3 (Factory system) - Major architectural change, consider deferring

## Recommended Order:
1. **Phase 4** (Quick win, low risk)
2. **Phase 2** (Protocol alignment)
3. **Phase 1** (Core dependency fixes)
4. **Phase 3** (Consider deferring or implementing incrementally)

## Success Metrics:
- **Primary:** 0 `# type: ignore` comments in codebase
- **Secondary:** 0 mypy errors
- **Tertiary:** All tests passing
- **Quality:** No loss of type safety or functionality

## Notes:
- Some type ignores may be acceptable long-term if they represent genuine limitations
- Focus on fixing the root causes rather than just changing the ignore comments
- Consider if any ignores represent actual design issues that should be addressed architecturally
