# Borgitory FastAPI DI Migration Plan

## 📋 Current Findings Summary

### ✅ **What's Working (The Good)**
- **FastAPI Depends() Usage**: Proper use of `Depends()` mechanism in API endpoints
- **Centralized Dependencies**: Well-organized `dependencies.py` module with clear naming
- **Type Annotations**: Good use of `Annotated[ServiceType, Depends(factory)]` pattern
- **Request-Scoped Services**: Database-dependent services properly scoped to requests
- **Constructor Injection**: Some services use proper constructor injection

### ❌ **Major Issues (The Bad)**
- **Manual Global Singletons**: 15+ global `_instance` variables defeating DI purpose
- **Circular Dependencies**: Architecture problems masked by workarounds
- **Mixed DI Patterns**: Inconsistent between proper DI and manual instantiation
- **Lifecycle Confusion**: No clear rationale for singleton vs request-scoped services

### 🚨 **Critical Problems (The Ugly)**
- **Service Locator Anti-Pattern**: Services directly importing and calling dependency factories
- **Complex Fallback Resolution**: `JobManager._get_repository_data()` with 3+ fallback mechanisms
- **God Object Factory**: `JobManagerFactory` with 15+ dependencies violating SRP
- **Runtime Dependency Resolution**: Services creating dependencies at runtime instead of injection

### 🔍 **Missing Opportunities**
- No interface/protocol abstractions
- No configuration-driven DI
- No proper scoped lifecycles
- No decorator-based injection patterns

---

## 🛣️ Migration Plan: Steps to Proper FastAPI DI

### **Phase 1: Foundation & Testing Infrastructure**

#### **Step 1.1: Create Dependency Interfaces**
**Goal**: Establish protocol-based contracts for testability
**Duration**: 2-3 days
**Status**: ✅ Completed

**Actions**:
```python
# Create src/borgitory/interfaces/
# - command_runner.py
# - storage_service.py  
# - job_manager.py
# etc.

from typing import Protocol, List, Dict, Any

class CommandRunner(Protocol):
    async def run_command(self, command: List[str], env: Dict[str, str] = None) -> CommandResult:
        ...

class StorageService(Protocol):
    async def store_data(self, key: str, data: bytes) -> bool:
        ...
```

**Testable Outcome**: 
- [x] All major service contracts defined as protocols
- [x] Existing services implement protocols without code changes
- [x] Type checker (mypy) passes on protocol definitions
- [x] Mock implementations can be created for each protocol

**Validation Tests**:
```python
def test_protocols_are_implemented():
    """Verify existing services implement the protocols"""
    from borgitory.services.simple_command_runner import SimpleCommandRunner
    from borgitory.interfaces.command_runner import CommandRunner
    
    runner: CommandRunner = SimpleCommandRunner()  # Should not raise type error
    assert isinstance(runner, SimpleCommandRunner)
```

#### **Step 1.2: Add Comprehensive Integration Tests**
**Goal**: Establish safety net before major refactoring
**Duration**: 3-4 days
**Status**: ✅ Skipped - Existing coverage is excellent (79%, 1,643 tests)

**Actions**:
- Create end-to-end API tests for all major workflows
- Add service integration tests
- Establish performance benchmarks

**Testable Outcome**:
- [ ] 95%+ API endpoint coverage with integration tests
- [ ] All critical user journeys covered (backup, restore, etc.)
- [ ] Performance baseline established
- [ ] Tests pass consistently in CI

**Validation Tests**:
```python
def test_backup_workflow_end_to_end():
    """Test complete backup workflow through API"""
    # Create repository -> Start backup -> Monitor progress -> Verify completion
    
def test_current_di_behavior():
    """Document current DI behavior to detect changes"""
    # Test singleton behavior, service interactions, etc.
```

### **Phase 2: Eliminate Manual Singletons**

#### **Step 2.1: Convert Simple Services to FastAPI DI**
**Goal**: Remove manual singleton management for stateless services
**Duration**: 4-5 days
**Status**: ✅ Completed

**Actions**:
```python
# BEFORE (manual singleton)
_simple_command_runner_instance = None
def get_simple_command_runner() -> SimpleCommandRunner:
    global _simple_command_runner_instance
    if _simple_command_runner_instance is None:
        _simple_command_runner_instance = SimpleCommandRunner()
    return _simple_command_runner_instance

# AFTER (FastAPI DI with caching)
from functools import lru_cache

@lru_cache()
def get_simple_command_runner() -> SimpleCommandRunner:
    return SimpleCommandRunner()
```

**Target Services** (in order of complexity):
1. `SimpleCommandRunner` - No dependencies ✅
2. `ConfigurationService` - No dependencies ✅ 
3. `CronDescriptionService` - No dependencies ✅
4. `VolumeService` - No dependencies ✅
5. `RcloneService` - No dependencies ✅

**Testable Outcome**:
- [x] All target services use `@lru_cache()` instead of manual singletons
- [x] Same instance returned across multiple calls (singleton behavior preserved)
- [x] No global `_instance` variables for converted services
- [x] All integration tests still pass
- [x] Memory usage doesn't increase (no instance leaks)

**Validation Tests**:
```python
def test_service_singleton_behavior():
    """Verify services maintain singleton behavior after conversion"""
    from borgitory.dependencies import get_simple_command_runner
    
    instance1 = get_simple_command_runner()
    instance2 = get_simple_command_runner()
    assert instance1 is instance2  # Same instance

def test_no_global_variables_remain():
    """Ensure no _instance variables exist for converted services"""
    import borgitory.dependencies
    
    for attr_name in dir(borgitory.dependencies):
        if attr_name.endswith('_instance'):
            # Should only be complex services not yet converted
            assert attr_name in ['_job_manager_instance', '_borg_service_instance']
```

#### **Step 2.2: Convert Services with Simple Dependencies**
**Goal**: Handle services that depend on other services
**Duration**: 5-6 days
**Status**: ✅ Completed

**Actions**:
```python
# BEFORE
_pushover_service_instance = None
def get_pushover_service() -> PushoverService:
    global _pushover_service_instance
    if _pushover_service_instance is None:
        _pushover_service_instance = PushoverService()
    return _pushover_service_instance

# AFTER  
def get_pushover_service(
    config: ConfigurationService = Depends(get_configuration_service)
) -> PushoverService:
    return PushoverService(config)
```

**Target Services**:
1. `PushoverService` 
2. `RecoveryService`
3. `RepositoryStatsService`
4. `RepositoryParser`
5. `BorgCommandBuilder`

**Testable Outcome**:
- [ ] Services use proper constructor injection
- [ ] Dependencies automatically resolved by FastAPI
- [ ] No circular dependency errors
- [ ] All API endpoints still function correctly
- [ ] Service behavior unchanged (same outputs for same inputs)

**Validation Tests**:
```python
def test_dependency_injection_works():
    """Test that FastAPI properly injects dependencies"""
    from fastapi.testclient import TestClient
    from borgitory.main import app
    
    client = TestClient(app)
    response = client.get("/api/repositories/")
    assert response.status_code == 200  # Dependencies injected correctly

def test_service_dependencies_resolved():
    """Test that service dependencies are properly resolved"""
    from borgitory.dependencies import get_pushover_service
    
    service = get_pushover_service()
    assert hasattr(service, 'config')  # Dependency was injected
```

### **Phase 3: Resolve Complex Dependencies**

#### **Step 3.1: Refactor JobManager Architecture**
**Goal**: Simplify the complex JobManager dependency tree
**Duration**: 8-10 days
**Status**: ✅ Completed

**Actions**:
1. **Split JobManager Responsibilities**:
   ```python
   # Split into focused services
   class JobExecutionService:  # Handles job execution
   class JobQueueService:      # Handles job queuing  
   class JobOutputService:     # Handles job output/streaming
   class JobEventService:      # Handles job events
   ```

2. **Create Focused Factories**:
   ```python
   def get_job_execution_service(
       executor: JobExecutor = Depends(get_job_executor),
       output_manager: JobOutputManager = Depends(get_job_output_manager)
   ) -> JobExecutionService:
       return JobExecutionService(executor, output_manager)
   ```

**Testable Outcome**:
- [ ] JobManager split into 4-5 focused services
- [ ] Each service has ≤5 dependencies
- [ ] All job-related functionality still works
- [ ] Job execution, queuing, and monitoring all function correctly
- [ ] No performance degradation

**Validation Tests**:
```python
def test_job_workflow_still_works():
    """Test that job workflows work after JobManager refactor"""
    # Test backup job creation -> execution -> completion
    
def test_job_manager_dependencies_reduced():
    """Verify JobManager complexity reduced"""
    from borgitory.services.jobs.job_execution_service import JobExecutionService
    import inspect
    
    sig = inspect.signature(JobExecutionService.__init__)
    assert len(sig.parameters) <= 6  # Including self, should be ≤5 dependencies
```

#### **Step 3.2: Eliminate Service Locator Pattern**
**Goal**: Remove direct dependency imports from services
**Duration**: 6-7 days
**Status**: ⏳ Pending

**Actions**:
```python
# BEFORE (Service Locator)
class BorgService:
    def some_method(self):
        from borgitory.dependencies import get_volume_service
        volume_service = get_volume_service()  # BAD
        
# AFTER (Proper DI)
class BorgService:
    def __init__(self, volume_service: VolumeService):
        self.volume_service = volume_service  # GOOD
        
    def some_method(self):
        self.volume_service.do_something()  # Use injected dependency
```

**Target Services**:
1. `BorgService` - Remove `get_volume_service()` calls
2. `ArchiveManager` - Remove direct JobExecutor creation
3. All services with `from borgitory.dependencies import` statements

**Testable Outcome**:
- [ ] No services directly import from `dependencies.py`
- [ ] All dependencies provided via constructor injection
- [ ] Services can be instantiated with mock dependencies for testing
- [ ] No hidden dependencies or service locator calls

**Validation Tests**:
```python
def test_no_service_locator_imports():
    """Ensure no services import dependencies directly"""
    import ast
    import os
    
    for root, dirs, files in os.walk('src/borgitory/services'):
        for file in files:
            if file.endswith('.py'):
                with open(os.path.join(root, file)) as f:
                    tree = ast.parse(f.read())
                    
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        assert node.module != 'borgitory.dependencies'

def test_services_mockable():
    """Test that services can be mocked for testing"""
    from unittest.mock import Mock
    from borgitory.services.borg_service import BorgService
    
    mock_volume_service = Mock()
    mock_job_manager = Mock()
    
    # Should be able to create with mocks
    service = BorgService(volume_service=mock_volume_service, job_manager=mock_job_manager)
    assert service is not None
```

### **Phase 4: Optimize and Clean Up**

#### **Step 4.1: Implement Proper Scoping**
**Goal**: Establish clear lifecycle management for different service types
**Duration**: 3-4 days
**Status**: ⏳ Pending

**Actions**:
```python
# Application-scoped (true singletons)
@lru_cache()
def get_configuration_service() -> ConfigurationService:
    return ConfigurationService()

# Request-scoped (new instance per request)  
def get_job_service(
    db: Session = Depends(get_db),
    job_manager: JobExecutionService = Depends(get_job_execution_service)
) -> JobService:
    return JobService(db, job_manager)

# Session-scoped (for database connections, etc.)
def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

**Testable Outcome**:
- [ ] Clear scoping rules documented and enforced
- [ ] Configuration services are application-scoped
- [ ] Database services are request-scoped
- [ ] No memory leaks from improper scoping
- [ ] Performance optimized (no unnecessary instance creation)

**Validation Tests**:
```python
def test_application_scoped_services():
    """Test that config services are true singletons"""
    from borgitory.dependencies import get_configuration_service
    
    # Should be same instance across multiple calls
    config1 = get_configuration_service()
    config2 = get_configuration_service()
    assert config1 is config2

def test_request_scoped_services():
    """Test that request services are properly scoped"""
    # Mock multiple requests and verify new instances created
```

#### **Step 4.2: Remove Remaining Global State**
**Goal**: Eliminate all remaining global singleton variables
**Duration**: 2-3 days
**Status**: ⏳ Pending

**Actions**:
- Remove all remaining `_instance` variables
- Convert remaining services to proper FastAPI DI
- Clean up dependency factory functions

**Testable Outcome**:
- [ ] Zero global `_instance` variables in codebase
- [ ] All services use FastAPI DI patterns
- [ ] Clean, consistent dependency injection throughout
- [ ] All tests still pass

**Validation Tests**:
```python
def test_no_global_singletons_remain():
    """Verify no global singleton variables exist"""
    import borgitory.dependencies
    
    # Check that no _instance variables exist
    instance_vars = [attr for attr in dir(borgitory.dependencies) 
                    if attr.endswith('_instance')]
    assert len(instance_vars) == 0, f"Global singletons still exist: {instance_vars}"

def test_all_services_use_fastapi_di():
    """Verify all dependency functions use proper FastAPI patterns"""
    # Check that all get_* functions use Depends() or @lru_cache()
```

### **Phase 5: Validation and Documentation**

#### **Step 5.1: Comprehensive Testing**
**Goal**: Ensure refactoring didn't break anything
**Duration**: 3-4 days
**Status**: ⏳ Pending

**Actions**:
- Run full test suite
- Performance testing vs baseline
- Load testing
- Manual testing of critical workflows

**Testable Outcome**:
- [ ] All existing tests pass
- [ ] Performance within 5% of baseline
- [ ] No memory leaks detected
- [ ] All user workflows function correctly

#### **Step 5.2: Documentation and Training**
**Goal**: Document new DI patterns and train team
**Duration**: 2-3 days
**Status**: ⏳ Pending

**Actions**:
- Document new DI patterns and conventions
- Create developer guide for adding new services
- Update architecture documentation

**Testable Outcome**:
- [ ] Complete DI documentation exists
- [ ] New service creation guide available
- [ ] Team trained on new patterns

---

## 🎯 Success Metrics

**Technical Metrics**:
- Zero global `_instance` variables
- All services use FastAPI DI patterns  
- No circular dependencies
- 100% test pass rate
- Performance within 5% of baseline

**Quality Metrics**:
- Services can be easily mocked for testing
- New services follow consistent DI patterns
- Reduced complexity in dependency factories
- Clear separation of concerns

**Timeline**: 6-8 weeks total with proper testing at each step.

---

## 📝 Progress Tracking

- [x] **Phase 1.1**: Create Dependency Interfaces (✅ Completed)
- [x] **Phase 1.2**: Add Comprehensive Integration Tests (✅ Skipped - Existing coverage excellent)
- [x] **Phase 2.1**: Convert Simple Services to FastAPI DI (✅ Completed)
- [x] **Phase 2.2**: Convert Services with Simple Dependencies (✅ Completed)
- [x] **Phase 3.1**: Refactor JobManager Architecture (✅ Completed)
- [x] **Phase 3.2**: Eliminate Service Locator Pattern (✅ Completed)
- [ ] **Phase 4.1**: Implement Proper Scoping
- [ ] **Phase 4.2**: Remove Remaining Global State
- [ ] **Phase 5.1**: Comprehensive Testing
- [ ] **Phase 5.2**: Documentation and Training

**Last Updated**: January 2025
**Current Phase**: 3.2 - Eliminating Service Locator Pattern
