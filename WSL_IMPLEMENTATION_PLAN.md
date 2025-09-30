# WSL Implementation Plan for Borgitory

## Overview

This document outlines the implementation plan for adding Windows Subsystem for Linux (WSL) support to Borgitory, enabling seamless operation on Windows by using WSL for all filesystem operations and borg commands.

## Current State

✅ **Completed:**
- Simplified path service architecture with `LinuxPathService`
- Removed Windows-specific path handling logic
- Updated schemas to accept only Unix-style paths (`/mnt/c/...`)
- Updated autocomplete to work with Unix paths
- Dependency injection infrastructure ready for WSL backend

## Implementation Phases

### Phase 1: WSL Detection and Command Wrapper 🚧 **IN PROGRESS**

#### 1.1 WSL Detection Service
- **File**: `src/borgitory/services/wsl/wsl_detection_service.py`
- **Purpose**: Detect WSL availability and configuration
- **Features**:
  - Check if WSL is installed (`wsl --version`)
  - Verify default WSL distribution
  - Check if borg is installed in WSL
  - Validate WSL filesystem access

#### 1.2 WSL Command Executor
- **File**: `src/borgitory/services/wsl/wsl_command_executor.py`
- **Purpose**: Execute commands through WSL
- **Features**:
  - Wrap commands with `wsl` prefix
  - Handle command arguments and environment variables
  - Async subprocess execution
  - Error handling and logging

#### 1.3 Path Translation Service
- **File**: `src/borgitory/services/wsl/wsl_path_translator.py`
- **Purpose**: Convert between Windows and WSL paths
- **Features**:
  - Windows to WSL: `C:\data` → `/mnt/c/data`
  - WSL to Windows: `/mnt/c/data` → `C:\data`
  - Handle UNC paths, network drives
  - Validate path accessibility

### Phase 2: WSL Filesystem Operations

#### 2.1 WSL Filesystem Service
- **File**: `src/borgitory/services/wsl/wsl_filesystem_service.py`
- **Purpose**: Filesystem operations via WSL
- **Features**:
  - Directory listing: `wsl ls -la /path`
  - Path existence: `wsl test -e /path`
  - Directory creation: `wsl mkdir -p /path`
  - File operations via WSL commands

#### 2.2 WSL Path Service Implementation
- **File**: `src/borgitory/services/path/wsl_path_service.py`
- **Purpose**: WSL-aware PathServiceInterface implementation
- **Features**:
  - Integrate WSL filesystem service
  - Handle Windows/WSL path translation
  - Maintain security (path traversal prevention)

### Phase 3: Borg Integration

#### 3.1 WSL Borg Command Builder
- **File**: `src/borgitory/services/wsl/wsl_borg_service.py`
- **Purpose**: Build borg commands for WSL execution
- **Features**:
  - Translate all path arguments to WSL format
  - Handle environment variables in WSL context
  - Manage keyfiles in WSL-accessible locations

#### 3.2 Update Existing Services
- **Files**: Various borg-related services
- **Purpose**: Use WSL command executor when on Windows
- **Features**:
  - Conditional WSL usage based on platform detection
  - Maintain backward compatibility with Unix systems

### Phase 4: Directory Browsing & Autocomplete

#### 4.1 WSL Directory Browser
- **File**: `src/borgitory/services/wsl/wsl_directory_service.py`
- **Purpose**: Browse filesystem via WSL
- **Features**:
  - List directories with metadata
  - Handle Windows drive mounting (`/mnt/c`, `/mnt/d`)
  - Detect borg repositories and caches

#### 4.2 Update Autocomplete System
- **Files**: `src/borgitory/api/repositories.py`, templates
- **Purpose**: Use WSL for directory browsing
- **Features**:
  - Show Windows drives as `/mnt/c`, `/mnt/d`
  - Seamless browsing across Windows filesystem
  - Maintain existing UI/UX

### Phase 5: Configuration & Integration

#### 5.1 Factory Updates
- **File**: `src/borgitory/services/path/path_service_factory.py`
- **Purpose**: Auto-select WSL vs native implementation
- **Logic**:
```python
def create_path_service() -> PathServiceInterface:
    config = PathConfigurationService()
    if config.is_windows() and wsl_available():
        return WSLPathService(config)
    else:
        return LinuxPathService(config)
```

#### 5.2 Configuration Options
- **File**: Environment variables and settings
- **Purpose**: Control WSL behavior
- **Options**:
  - `BORGITORY_USE_WSL=true/false` - Force WSL on/off
  - `BORGITORY_WSL_DISTRO=Ubuntu` - Specify WSL distribution
  - `BORGITORY_WSL_TIMEOUT=30` - Command timeout

### Phase 6: Testing & Polish

#### 6.1 WSL-Specific Tests
- **Files**: `tests/services/wsl/`
- **Purpose**: Comprehensive WSL testing
- **Coverage**:
  - WSL detection and availability
  - Path translation accuracy
  - Command execution
  - Filesystem operations
  - Integration with existing services

#### 6.2 Cross-Platform Testing
- **Purpose**: Ensure no regressions
- **Coverage**:
  - Native Unix systems (Linux, macOS)
  - Container environments
  - Windows with WSL
  - Windows without WSL (graceful fallback)

## Technical Considerations

### WSL Path Mapping
```
Windows Path          WSL Path
C:\data              /mnt/c/data
D:\backups           /mnt/d/backups
\\server\share       /mnt/server/share (if mounted)
```

### Command Translation Examples
```python
# Native Windows (current - doesn't work)
["borg", "create", "C:\\repo::archive", "C:\\source"]

# WSL Translation (target)
["wsl", "borg", "create", "/mnt/c/repo::archive", "/mnt/c/source"]
```

### Error Handling Strategy
1. **WSL Not Available**: Graceful fallback to error message
2. **Borg Not Installed in WSL**: Clear installation instructions
3. **Path Access Issues**: Detailed error reporting
4. **WSL Command Failures**: Pass through WSL error messages

### Performance Considerations
- **Command Overhead**: WSL adds ~50-100ms per command
- **Filesystem I/O**: Cross-boundary operations can be slower
- **Caching Strategy**: Cache WSL availability and path translations
- **Batch Operations**: Group multiple filesystem operations when possible

## Implementation Order

1. ✅ **Foundation**: Simplified path architecture (DONE)
2. 🚧 **WSL Detection**: Basic WSL availability checking
3. **Command Wrapper**: WSL command execution infrastructure
4. **Path Translation**: Windows ↔ WSL path conversion
5. **Filesystem Service**: WSL-based directory operations
6. **Borg Integration**: WSL-aware borg command execution
7. **Factory Integration**: Auto-selection of WSL vs native
8. **Testing & Polish**: Comprehensive testing and edge cases

## Success Criteria

- ✅ Windows users can run `pip install borgitory` and it works
- ✅ All filesystem browsing works through WSL
- ✅ All borg operations execute via WSL
- ✅ No changes required to existing templates/UI
- ✅ Graceful fallback when WSL unavailable
- ✅ Performance acceptable for typical operations
- ✅ No regressions on Unix systems

## Next Steps

1. **Start with WSL Detection Service** - Basic foundation
2. **Implement Command Executor** - Core WSL integration
3. **Add Path Translation** - Windows/WSL path handling
4. **Update Factory** - Auto-selection logic
5. **Test Integration** - Ensure everything works together
