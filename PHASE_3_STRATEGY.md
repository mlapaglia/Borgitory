# Phase 3 Strategy: Type-Safe Factory System

## Risk Assessment & Mitigation Strategy

### Current Issues Analysis

#### Issue 1: Function vs Class Type Mismatch
```
Argument 2 to "register_implementation" has incompatible type 
"Callable[[KwArg(Any)], BackupServiceProtocol]"; expected "type[BackupServiceProtocol]"
```
**Root Cause:** `register_implementation` expects a class type, but we're passing a factory function.

#### Issues 2-4: Generic Return Type Casting
```
Incompatible return value type (got "ServiceFactory[Any]", expected "NotificationServiceFactory")
```
**Root Cause:** `get_factory()` returns `ServiceFactory[Any]` but convenience methods expect specific subtypes.

## Strategy Options (Ranked by Risk)

### Option 1: MINIMAL RISK - Targeted Type Fixes
**Risk Level:** 🟢 Low  
**Effort:** Low  
**Approach:** Fix each issue with minimal changes

1. **Fix Function Registration Issue**
   - Create a wrapper class for `create_borg_service` function
   - Or use `Union[Type[P], Callable[..., P]]` in registration

2. **Fix Generic Return Types**  
   - Use `cast()` function instead of type ignore
   - Add runtime type checking for safety

**Pros:** Minimal code changes, maintains current architecture
**Cons:** Still not "pure" type safety, uses casting

### Option 2: MODERATE RISK - Hybrid Approach
**Risk Level:** 🟡 Medium  
**Effort:** Medium  
**Approach:** Selective architectural improvements

1. **Factory Function Support**
   - Extend `ServiceFactory` to accept both classes and factory functions
   - Add proper type annotations for both cases

2. **Typed Registry Methods**
   - Use `@overload` decorators for type-safe `get_factory()` calls
   - Maintain backward compatibility

**Pros:** Better type safety, supports both patterns
**Cons:** More complex generic system

### Option 3: HIGH RISK - Complete Redesign  
**Risk Level:** 🔴 High  
**Effort:** High  
**Approach:** Full architectural overhaul

1. **Separate Factory Types**
   - Create distinct factories for classes vs functions
   - Implement proper generic constraints

2. **Type-Safe Registry**
   - Replace string-based lookup with type-safe methods
   - Use dependency injection container pattern

**Pros:** Perfect type safety, clean architecture
**Cons:** Major breaking changes, high complexity

## Recommended Strategy: Progressive Implementation

### Phase 3A: Quick Wins (Low Risk)
**Goal:** Eliminate type ignores with minimal changes

1. **Fix Function Registration**
   ```python
   # Current problematic approach
   self.register_implementation("borg", create_borg_service)
   
   # Solution: Create wrapper class
   class BorgServiceFactory:
       def __init__(self, **kwargs):
           return create_borg_service(**kwargs)
   
   self.register_implementation("borg", BorgServiceFactory)
   ```

2. **Fix Return Type Casting**
   ```python
   # Instead of type: ignore, use explicit cast with runtime check
   def get_notification_factory(self) -> NotificationServiceFactory:
       factory = self.get_factory("notifications")
       assert isinstance(factory, NotificationServiceFactory)
       return cast(NotificationServiceFactory, factory)
   ```

### Phase 3B: Architectural Improvements (Medium Risk) - OPTIONAL
**Goal:** Improve type safety without breaking changes

1. **Support Factory Functions**
   ```python
   ImplementationType = Union[Type[P], Callable[..., P]]
   
   def register_implementation(
       self, 
       name: str, 
       implementation: ImplementationType[P],
       ...
   ):
   ```

2. **Overloaded Registry Methods**
   ```python
   @overload
   def get_factory(self, name: Literal["notifications"]) -> NotificationServiceFactory: ...
   @overload
   def get_factory(self, name: Literal["command_runners"]) -> CommandRunnerFactory: ...
   ```

## Implementation Plan

### Step 1: Backup & Test Baseline
- [x] Create comprehensive tests for current factory behavior
- [x] Ensure 1734+ tests pass before changes
- [x] Document current API contracts

### Step 2: Phase 3A Implementation (RECOMMENDED START)
1. **Fix BorgService Registration**
   - Create proper class wrapper for `create_borg_service`
   - Test that factory still works correctly

2. **Fix Generic Return Types**
   - Replace type ignores with `cast()` + assertions
   - Add runtime type validation

3. **Validate Changes**
   - Run full test suite
   - Verify mypy passes with 0 errors
   - Confirm no functional regressions

### Step 3: Phase 3B Implementation (OPTIONAL)
- Only proceed if Phase 3A succeeds
- Implement architectural improvements incrementally
- Maintain backward compatibility throughout

## Risk Mitigation Checklist

### Before Implementation
- [ ] Run full test suite (expect 1734+ passing)
- [ ] Document current factory usage patterns
- [ ] Create rollback plan

### During Implementation  
- [ ] Implement changes incrementally (one issue at a time)
- [ ] Run tests after each change
- [ ] Verify mypy passes at each step

### After Implementation
- [ ] Full test suite passes
- [ ] Zero mypy errors
- [ ] Zero type ignore comments
- [ ] No functional regressions
- [ ] Performance benchmarks unchanged

## Success Criteria

### Primary Goals
- ✅ Zero `# type: ignore` comments in factory system
- ✅ Zero mypy errors
- ✅ All existing tests pass

### Secondary Goals  
- ✅ Improved type safety
- ✅ Maintainable code structure
- ✅ Clear error messages

## Rollback Plan

If any step fails:
1. **Immediate:** Restore type ignore comments
2. **Verify:** All tests pass with ignores restored  
3. **Analyze:** Determine root cause of failure
4. **Decide:** Retry with different approach or defer Phase 3

## Recommendation

**START WITH PHASE 3A** - This gives us the wins we need (zero type ignores) with minimal risk. Phase 3B can be considered later as a separate improvement initiative.

The key insight: **Perfect type safety is less important than zero regressions and maintainable code.**
