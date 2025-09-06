# Session Lifecycle Issues Analysis

## Critical Issues Found

### 1. FastAPI Routes with Manual Session Management ✅ FIXED
- **Files**: `app/main.py`
- **Issue**: Routes using `next(get_db())` instead of dependency injection
- **Risk**: Sessions not closed on exceptions
- **Fix**: Updated to use `db: Session = Depends(get_db)`

### 2. Service Classes with Incomplete Error Handling 
- **Files**: Multiple service files
- **Issues**:
  - Missing `db.rollback()` in exception handlers
  - Missing `finally` blocks for cleanup
  - Manual session management without context managers

### 3. Specific Problematic Locations

#### job_manager.py:
- ✅ **Line 166**: Fixed - now uses context manager
- ✅ **Line 883**: Fixed - now uses context manager  
- ✅ **Line 1052**: Fixed - now uses context manager
- ✅ **Line 1085**: Fixed - now uses context manager

#### scheduler_service.py:
- ✅ **Line 27**: Fixed - now uses context manager
- ✅ **Line 239**: Fixed - now uses context manager 
- ✅ **Line 316**: Fixed - now uses context manager

#### recovery_service.py:
- ✅ **Line 49**: Fixed - now uses context manager

#### composite_job_manager.py:
- ✅ **Line 83**: Fixed - now uses context manager
- ✅ **Multiple lines**: All session leaks fixed

#### borg_service.py:
- ✅ **Line 267**: Fixed - now uses context manager
- ✅ **Line 306**: Fixed - now uses context manager

## Recommended Fixes

### Immediate Priority (Critical - Resource Leaks)
1. ✅ Fix FastAPI routes to use dependency injection
2. ✅ Add context manager utility (`app/utils/db_session.py`)  
3. ✅ Fix scheduler_service.py (runs continuously)
4. ✅ Fix recovery_service.py (runs at startup)

### Medium Priority (Performance Impact)
1. ✅ Fix job_manager.py remaining issues
2. ✅ Fix composite_job_manager.py  
3. ✅ Fix borg_service.py

### Long-term (Best Practice)  
1. Create migration to use decorators/context managers
2. Add linting rules to catch `next(get_db())` patterns
3. Add session monitoring/metrics

## Impact Assessment

**Critical Risk**: 
- Scheduler runs continuously - session leaks cause memory growth
- Recovery service runs at startup - could cause startup failures
- Manual routes - user-facing functionality affected

**Performance Impact**:
- Database connection pool exhaustion
- Memory leaks in long-running processes  
- Potential deadlocks with uncommitted transactions

## Solution: Context Manager Approach

Created `app/utils/db_session.py` with:
- `get_db_session()` - Auto-commit with rollback on error
- `get_db_session_no_commit()` - Read-only sessions
- `@db_transaction` and `@db_readonly` decorators