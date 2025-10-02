"""
Path services package for filesystem operations.

This package provides a unified path service that abstracts filesystem operations
for different environments using dependency injection.
"""

from borgitory.services.path.path_service_factory import (
    create_path_service,
    get_path_service,
)
from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.services.path.path_service import PathService
from borgitory.protocols.path_protocols import (
    PathServiceInterface,
    PathConfigurationInterface,
)

__all__ = [
    "create_path_service",
    "get_path_service",
    "PathConfigurationService",
    "PathService",
    "PathServiceInterface",
    "PathConfigurationInterface",
]
