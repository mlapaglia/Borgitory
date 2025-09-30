# Simplified Cross-Platform Path Handling Solution

## Overview

This document describes the simplified cross-platform path handling solution for Borgitory that provides filesystem abstraction through dependency injection while preparing for WSL integration on Windows.

## Problem Statement

The original Borgitory application had hardcoded Linux-specific paths that would fail when running as a pip-installed application on Windows:

- **Hardcoded paths**: `/app/data/keyfiles`, `/tmp/borgitory-mounts`
- **Platform assumptions**: Assumed Unix-style directory structures
- **No environment detection**: No distinction between container vs native execution
- **Complex path handling**: Need for Windows/Unix path compatibility

## Solution Architecture

### Core Components

1. **PathServiceInterface** - Abstract interface defining filesystem operations
2. **LinuxPathService** - Single implementation that works across platforms
3. **PathConfigurationService** - Environment detection and base path determination
4. **Factory Pattern** - Clean dependency injection integration

### Key Design Decisions

#### Simplified Implementation
- **Single service class** instead of platform-specific implementations
- **Environment-based configuration** rather than platform-specific logic
- **Pathlib-based operations** for robust cross-platform path handling
- **Security-first approach** with path traversal prevention

#### WSL-Ready Architecture
- **Abstract filesystem operations** to support future WSL integration
- **Dependency injection** allows easy swapping of implementations
- **Interface-based design** supports different backends (native, WSL, remote)

## Implementation Details

### Directory Structure
```
src/borgitory/
├── protocols/
│   └── path_protocols.py          # PathServiceInterface definition
└── services/path/
    ├── __init__.py
    ├── path_service_factory.py     # Factory function
    ├── path_configuration_service.py  # Environment detection
    └── linux_path_service.py   # Single implementation
```

### Key Features

#### Environment Detection
```python
class PathConfigurationService:
    def _detect_container_environment(self) -> bool:
        # Detects Docker/Kubernetes environments
        
    def _determine_platform_name(self) -> str:
        # Returns: "container", "windows", or "linux"
        
    def get_base_data_dir(self) -> str:
        # Platform-specific data directories:
        # Container: /app/data
        # Windows: %LOCALAPPDATA%\Borgitory  
        # Unix: ~/.local/share/borgitory
```

#### Universal Path Service
```python
class LinuxPathService(PathServiceInterface):
    def secure_join(self, base_path: str, *path_parts: str) -> str:
        # Prevents directory traversal attacks
        
    def ensure_directory(self, path: str) -> None:
        # Cross-platform directory creation
        
    def get_data_dir(self) -> str:
        # Uses PathConfigurationService for platform-specific paths
```

#### Factory Integration
```python
def create_path_service() -> PathServiceInterface:
    config = PathConfigurationService()
    return LinuxPathService(config)
```

### Dependency Injection Integration

The path service integrates cleanly with FastAPI's DI system:

```python
# In dependencies.py
PathServiceDep = Annotated["PathServiceInterface", Depends(get_path_service)]

# Usage in services
class RepositoryService:
    def __init__(self, path_service: PathServiceInterface):
        self.path_service = path_service
        
    async def _save_keyfile(self, repository_name: str, keyfile):
        keyfiles_dir = self.path_service.get_keyfiles_dir()
        keyfile_path = self.path_service.secure_join(keyfiles_dir, filename)
```

## Benefits

### Immediate Benefits
- **Simplified codebase**: Single implementation vs multiple platform classes
- **Reduced complexity**: No complex Windows/Unix path conversion logic
- **Better testing**: Easy to mock filesystem operations
- **Security**: Built-in path traversal prevention

### Future Benefits (WSL Integration)
- **Easy backend swapping**: Interface allows WSL implementation
- **Consistent API**: Same interface for native and WSL operations
- **Testable**: Can mock WSL operations for testing
- **Flexible**: Supports multiple execution environments

## Migration Path for WSL

When WSL support is added, the architecture will support:

1. **WSLPathService** - New implementation using WSL commands
2. **Path translation** - Windows paths to WSL paths (`C:\` → `/mnt/c/`)
3. **Command wrapping** - All filesystem operations via WSL
4. **Factory selection** - Automatic WSL vs native selection

Example future WSL integration:
```python
class WSLPathService(PathServiceInterface):
    async def list_directories(self, path: str) -> List[DirectoryInfo]:
        # Use: wsl ls -la /path
        
def create_path_service() -> PathServiceInterface:
    config = PathConfigurationService()
    if config.is_windows() and wsl_available():
        return WSLPathService(config)  # Future WSL implementation
    else:
        return LinuxPathService(config)  # Current implementation
```

## Testing

The simplified architecture is fully tested with:
- **Unit tests** for all path operations
- **Cross-platform tests** that work on Windows and Unix
- **Security tests** for path traversal prevention
- **Mock-based tests** for dependency injection

## Conclusion

This solution provides a clean, maintainable approach to cross-platform path handling while laying the groundwork for future WSL integration. The simplified architecture reduces complexity while maintaining all the benefits of dependency injection and interface-based design.