# Protocol Implementation Plan for Borgitory

## 🎯 **Objective**
Transform Borgitory from concrete dependency coupling to Protocol-based architecture while maintaining 100% backward compatibility and test coverage.

## 📊 **Current State Analysis**
- **1706 unit tests** currently passing
- **6 core services** with tight coupling: BorgService, JobManager, ArchiveManager, DebugService, RepositoryService, CloudSyncService
- **FastAPI DI system** already in place and working well
- **Test infrastructure** robust with dependency override capabilities

## 🚀 **Implementation Strategy: "Strangler Fig Pattern"**

We'll implement protocols alongside existing concrete classes, gradually migrating services one by one. This ensures:
- ✅ Zero breaking changes during migration
- ✅ Existing tests continue to pass
- ✅ New protocol-based tests validate behavior
- ✅ Rollback capability at any stage

---

## 📋 **Phase 1: Foundation & Core Protocols**
*Duration: 1-2 days*
*Risk: Low*

### Step 1.1: Complete Protocol Definitions
- ✅ **Already Done**: Basic protocols created
- 🔄 **Extend**: Add missing protocols for all service interfaces
- 📝 **Deliverable**: Complete protocol suite in `src/borgitory/protocols/`

**Files to Create/Update:**
```
src/borgitory/protocols/
├── __init__.py ✅
├── command_protocols.py ✅ 
├── storage_protocols.py ✅
├── job_protocols.py ✅
├── repository_protocols.py (new)
├── notification_protocols.py (new)
└── cloud_protocols.py (new)
```

**Test Coverage:**
- Create `tests/protocols/` directory
- Add protocol compliance tests
- Validate that existing services satisfy protocols

### Step 1.2: Protocol Validation Infrastructure
Create tooling to verify protocol compliance:

```python
# tests/protocols/test_protocol_compliance.py
def test_borg_service_satisfies_backup_protocol():
    """Verify BorgService implements BackupServiceProtocol"""
    from borgitory.services.borg_service import BorgService
    from borgitory.protocols.repository_protocols import BackupServiceProtocol
    
    # Runtime check that BorgService satisfies protocol
    assert hasattr(BorgService, 'create_backup')
    assert hasattr(BorgService, 'list_archives')
    # ... validate all protocol methods
```

**Success Criteria:**
- [ ] All protocols defined with proper type hints
- [ ] Protocol compliance tests pass for existing services
- [ ] No existing tests broken
- [ ] mypy validation passes

---

## 📋 **Phase 2: Service-by-Service Migration**
*Duration: 3-4 days*
*Risk: Medium*

We'll migrate services in dependency order (least dependent first):

### Step 2.1: SimpleCommandRunner → CommandRunnerProtocol
**Why First**: No dependencies on other services, used by many others

**Implementation:**
1. Update `SimpleCommandRunner` to naturally satisfy `CommandRunnerProtocol`
2. Create protocol-based tests
3. Update dependency injection to accept protocol
4. Verify all existing tests pass

```python
# Before (in dependencies.py)
def get_simple_command_runner() -> SimpleCommandRunner:
    return SimpleCommandRunner()

# After (backward compatible)
def get_simple_command_runner() -> CommandRunnerProtocol:
    return SimpleCommandRunner()  # Still returns concrete class
```

**Test Strategy:**
```python
# New protocol-based test
def test_command_runner_protocol():
    runner: CommandRunnerProtocol = get_simple_command_runner()
    result = await runner.run_command("echo test")
    assert result.success

# Existing tests continue to work unchanged
def test_simple_command_runner():
    runner = get_simple_command_runner()  # Still works
    # ... existing test logic
```

### Step 2.2: VolumeService → VolumeServiceProtocol
**Why Second**: Simple service, used by BorgService and DebugService

**Implementation:**
1. Ensure `VolumeService` satisfies `VolumeServiceProtocol`
2. Update DI to return protocol type
3. Create protocol-specific tests
4. Verify BorgService and DebugService still work

### Step 2.3: JobExecutor → ProcessExecutorProtocol
**Why Third**: Core execution service, used by many others

### Step 2.4: ArchiveManager → ArchiveServiceProtocol
**Why Fourth**: Self-contained service with minimal dependencies

### Step 2.5: BorgService → BackupServiceProtocol
**Why Fifth**: Major service, depends on protocols from steps 2.1-2.3

**Implementation:**
```python
# Update constructor to accept protocols
class BorgService:
    def __init__(
        self,
        command_runner: Optional[CommandRunnerProtocol] = None,  # Protocol!
        volume_service: Optional[VolumeServiceProtocol] = None,  # Protocol!
        job_manager: Optional[JobManagerProtocol] = None,        # Protocol!
    ):
        # Implementation remains the same
```

**Test Strategy:**
- Keep all existing BorgService tests (they should still pass)
- Add new protocol-based tests with mocks
- Add integration tests to verify protocol interactions

### Step 2.6: JobManager → JobManagerProtocol
**Why Sixth**: Complex service, depends on many others

### Step 2.7: Remaining Services
- DebugService
- RepositoryService  
- CloudSyncService
- NotificationService

**Success Criteria for Each Service:**
- [ ] Service naturally implements its protocol
- [ ] DI updated to use protocol types
- [ ] All existing tests pass
- [ ] New protocol-based tests added
- [ ] Integration tests verify protocol interactions
- [ ] mypy validation passes

---

## 📋 **Phase 3: Advanced Protocol Features**
*Duration: 2-3 days*
*Risk: Low*

### Step 3.1: Protocol Composition
Create composed protocols for complex operations:

```python
class BackupOperationProtocol(Protocol):
    """Combines multiple protocols for complete backup operations"""
    backup_service: BackupServiceProtocol
    storage_service: StorageServiceProtocol
    notification_service: NotificationServiceProtocol
```

### Step 3.2: Protocol-Based Factories
Update factories to work with protocols:

```python
class ServiceFactory:
    @staticmethod
    def create_backup_operation(
        config: BackupConfig
    ) -> BackupOperationProtocol:
        # Return implementation that satisfies protocol
        return BackupOperation(
            backup_service=BorgService(...),
            storage_service=VolumeService(...),
            notification_service=PushoverService(...)
        )
```

### Step 3.3: Configuration-Driven Protocol Selection
Allow runtime selection of implementations:

```python
# config.yaml
services:
  command_runner:
    implementation: "simple"  # or "async", "mock", etc.
  storage:
    implementation: "filesystem"  # or "s3", "redis", etc.
```

---

## 📋 **Phase 4: Testing & Validation**
*Duration: 1-2 days*
*Risk: Low*

### Step 4.1: Comprehensive Test Suite
- **Protocol Compliance Tests**: Verify all services implement their protocols
- **Integration Tests**: Test protocol interactions
- **Performance Tests**: Ensure no performance regression
- **Mock-based Tests**: Fast unit tests using protocol mocks

### Step 4.2: Documentation
- Update API documentation to show protocol usage
- Create developer guide for adding new implementations
- Document migration benefits and patterns

---

## 📋 **Phase 5: Cleanup & Optimization**
*Duration: 1 day*
*Risk: Low*

### Step 5.1: Remove Backward Compatibility Shims
Once all services use protocols, remove any temporary compatibility code.

### Step 5.2: Optimize Imports
Update imports to use protocols instead of concrete classes where possible.

---

## 🧪 **Testing Strategy Throughout Migration**

### Continuous Testing Approach:
1. **Before each step**: Run full test suite (should pass)
2. **During implementation**: Run affected tests continuously
3. **After each step**: Run full test suite (should still pass)
4. **Add new tests**: Protocol-specific tests for each migrated service

### Test Categories:

#### 1. **Regression Tests** (Existing)
```bash
# These should NEVER fail during migration
pytest tests/ --ignore=tests/protocols/
```

#### 2. **Protocol Compliance Tests** (New)
```bash
# Verify services implement protocols correctly
pytest tests/protocols/test_compliance.py
```

#### 3. **Protocol Integration Tests** (New)
```bash
# Test protocol interactions
pytest tests/protocols/test_integration.py
```

#### 4. **Mock-based Protocol Tests** (New)
```bash
# Fast unit tests using protocol mocks
pytest tests/protocols/test_mocking.py
```

### Test Infrastructure Updates:

#### Enhanced DI Testing:
```python
# tests/utils/protocol_testing.py
class ProtocolMockFactory:
    @staticmethod
    def create_command_runner_mock() -> CommandRunnerProtocol:
        mock = Mock(spec=CommandRunnerProtocol)
        mock.run_command = AsyncMock(return_value=CommandResult(0, b"", b""))
        return mock
```

#### Protocol-Aware Dependency Overrides:
```python
def override_with_protocol_mock(
    protocol_type: Type[Protocol], 
    mock_implementation: Any
) -> ContextManager:
    """Override any protocol with a mock implementation"""
    # Implementation details...
```

---

## 🚨 **Risk Mitigation**

### High-Risk Areas:
1. **JobManager**: Complex with many dependencies
2. **BorgService**: Core service with many dependents
3. **DI System**: Changes could break FastAPI integration

### Mitigation Strategies:
1. **Gradual Migration**: One service at a time
2. **Backward Compatibility**: Keep concrete types working
3. **Comprehensive Testing**: Test before, during, after each change
4. **Feature Flags**: Ability to rollback to concrete implementations
5. **Staging Environment**: Test full integration before production

### Rollback Plan:
Each phase can be independently rolled back:
- **Phase 1**: Remove protocol files
- **Phase 2**: Revert DI changes for specific services
- **Phase 3+**: Remove advanced features, keep basic protocols

---

## 📈 **Success Metrics**

### Quantitative Goals:
- [ ] **0 test failures** throughout migration
- [ ] **100% protocol compliance** for all migrated services
- [ ] **<5% performance impact** on critical paths
- [ ] **>90% test coverage** for protocol-based code

### Qualitative Goals:
- [ ] **Easier testing** with simple mocks
- [ ] **Flexible implementations** can be swapped
- [ ] **Cleaner architecture** with clear interfaces
- [ ] **Better maintainability** with isolated changes

---

## 📅 **Timeline Summary**

| Phase | Duration | Risk | Dependencies |
|-------|----------|------|--------------|
| 1. Foundation | 1-2 days | Low | None |
| 2. Service Migration | 3-4 days | Medium | Phase 1 |
| 3. Advanced Features | 2-3 days | Low | Phase 2 |
| 4. Testing & Validation | 1-2 days | Low | Phase 3 |
| 5. Cleanup | 1 day | Low | Phase 4 |

**Total: 8-12 days**

---

## 🎯 **Next Steps**

1. **Review this plan** with the team
2. **Set up development branch** for protocol implementation
3. **Begin Phase 1**: Complete protocol definitions
4. **Establish testing baseline**: Ensure all 1706 tests pass
5. **Start migration**: Begin with SimpleCommandRunner

---

## 📝 **Notes**

- This plan prioritizes **safety over speed** - we can accelerate if needed
- **Existing tests are our safety net** - they must always pass
- **Protocol implementation is additive** - we're not removing existing functionality
- **Benefits compound** - each migrated service makes the next easier
- **Rollback is always possible** - we maintain backward compatibility throughout

The protocol implementation will transform Borgitory into a more maintainable, testable, and extensible codebase while maintaining 100% reliability during the transition.
