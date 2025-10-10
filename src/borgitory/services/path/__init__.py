"""
Path services package for filesystem operations.

This package provides a unified path service that abstracts filesystem operations
for different environments using dependency injection.
"""

from borgitory.services.path.path_service_factory import (
    create_path_service,
    get_path_service,
)
from borgitory.services.path.path_service import PathService
from borgitory.protocols.path_protocols import (
    PathServiceInterface,
)

__all__ = [
    "create_path_service",
    "get_path_service",
    "PathService",
    "PathServiceInterface",
]
