# Borgitory Coupling Analysis

## Current Dependency Graph (Simplified)

```
BorgService 
├── imports JobExecutor (concrete)
├── imports SimpleCommandRunner (concrete)  
├── imports JobManager (concrete)
└── imports VolumeService (concrete)
    └── JobManager
        ├── imports JobExecutor (concrete)
        ├── imports JobOutputManager (concrete)
        ├── imports JobQueueManager (concrete)
        ├── imports JobEventBroadcaster (concrete)
        └── imports PushoverService (concrete)
            └── JobExecutor
                └── imports subprocess (system)
```

**Problems:**
- 🔴 **Circular Dependencies**: Services import each other
- 🔴 **Deep Coupling**: Changes ripple through multiple layers
- 🔴 **Single Points of Failure**: One service change breaks many others

## Impact on Development

### Testing Complexity
```python
# To test BorgService.scan_for_repositories():
# 1. Need working JobExecutor
# 2. Need working SimpleCommandRunner  
# 3. Need working VolumeService
# 4. Need working JobManager
#    - Which needs JobOutputManager
#    - Which needs JobQueueManager
#    - Which needs JobEventBroadcaster
#    - Which needs PushoverService
# 5. Need working database connection
# 6. Need working filesystem access

# Result: "Unit test" becomes integration test
# Time: 5+ seconds instead of milliseconds
# Flakiness: High (depends on external systems)
```

### Development Velocity
```python
# Want to add new feature to BorgService?
# 1. Must understand JobExecutor internals
# 2. Must understand SimpleCommandRunner internals
# 3. Must understand JobManager internals
# 4. Must understand VolumeService internals
# 5. Changes might break any of the above
# 6. Must run full integration test suite
# 7. Must coordinate changes across multiple modules

# Result: Simple changes become complex
# Time: Hours instead of minutes
# Risk: High (breaking changes across modules)
```

## The Protocol Solution

### After Protocol Implementation
```
BorgService
├── uses CommandRunnerProtocol (interface)
├── uses ProcessExecutorProtocol (interface)
├── uses JobManagerProtocol (interface)
└── uses VolumeServiceProtocol (interface)
```

**Benefits:**
- ✅ **No Concrete Dependencies**: Only depends on interfaces
- ✅ **Easy Testing**: Mock interfaces, not complex classes
- ✅ **Flexible Implementations**: Swap Redis for SQLite easily
- ✅ **Faster Development**: Change one implementation without affecting others

### Testing Becomes Simple
```python
def test_borg_service_scan():
    # 30 seconds to write, milliseconds to run
    mock_volume = Mock(spec=VolumeServiceProtocol)
    mock_volume.get_mounted_volumes.return_value = ["/test"]
    
    service = BorgService(volume_service=mock_volume)
    result = service.scan_for_repositories()
    
    assert result == expected_result
```

### Development Becomes Fast
```python
# Want to add caching to VolumeService?
class CachedVolumeService:  # Just implement the protocol
    def get_mounted_volumes(self): 
        return cache.get("volumes") or self._fetch_volumes()

# BorgService works immediately - no changes needed!
# Tests still pass - no changes needed!
# Other services unaffected - no changes needed!
```
