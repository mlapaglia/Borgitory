"""
Path services package for filesystem operations.

This package provides path services that abstract filesystem operations
for different environments (native, WSL, container).
"""

from borgitory.services.path.path_service_factory import (
    create_path_service,
    get_path_service,
)
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.services.path.universal_path_service import UniversalPathService
from borgitory.protocols.path_protocols import (
    PathServiceInterface,
    PathConfigurationInterface,
)

# WSL service is imported conditionally in factory to avoid import errors on non-Windows
try:
    from borgitory.services.path.wsl_path_service import WSLPathService

    _WSL_AVAILABLE = True
except ImportError:
    _WSL_AVAILABLE = False
    WSLPathService = None  # type: ignore

__all__ = [
    "create_path_service",
    "get_path_service",
    "PathConfigurationService",
    "UniversalPathService",
    "PathServiceInterface",
    "PathConfigurationInterface",
]

if _WSL_AVAILABLE:
    __all__.append("WSLPathService")
