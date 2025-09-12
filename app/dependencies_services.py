"""
Dependency injection for service layer.

Provides clean dependency injection for service interfaces,
making testing and maintenance much easier.
"""

from fastapi import Depends

from app.services.interfaces import RepositoryService, SecurityValidator, BorgServiceInterface
from app.services.implementations import (
    DefaultRepositoryService,
    DefaultBorgService,
    DefaultSecurityValidator
)

# Global instances for dependency injection
_security_validator: SecurityValidator = DefaultSecurityValidator()
_borg_service: BorgServiceInterface = None
_repository_service: RepositoryService = None


def get_security_validator() -> SecurityValidator:
    """Get security validator instance."""
    return _security_validator


def get_borg_service_interface() -> BorgServiceInterface:
    """Get Borg service interface instance."""
    global _borg_service
    if _borg_service is None:
        # Use the existing dependency system which respects test overrides
        from app.dependencies import get_borg_service
        actual_borg_service = get_borg_service()
        _borg_service = DefaultBorgService(actual_borg_service)
    return _borg_service


def get_repository_service() -> RepositoryService:
    """Get repository service instance."""
    global _repository_service
    if _repository_service is None:
        _repository_service = DefaultRepositoryService(
            get_security_validator(),
            get_borg_service_interface()
        )
    return _repository_service


# Functions to override dependencies for testing
def set_borg_service(borg_service: BorgServiceInterface):
    """Override borg service for testing."""
    global _borg_service, _repository_service
    _borg_service = borg_service
    _repository_service = None  # Reset to rebuild with new dependency


def set_repository_service(repository_service: RepositoryService):
    """Override repository service for testing."""
    global _repository_service
    _repository_service = repository_service


def reset_dependencies():
    """Reset all dependencies - useful for testing."""
    global _security_validator, _borg_service, _repository_service
    _security_validator = DefaultSecurityValidator()
    _borg_service = None
    _repository_service = None


# FastAPI dependency functions
def get_repository_service_dep() -> RepositoryService:
    """FastAPI dependency for repository service."""
    return get_repository_service()


def get_security_validator_dep() -> SecurityValidator:
    """FastAPI dependency for security validator."""
    return get_security_validator()


# Type aliases for cleaner API signatures
RepositoryServiceDep = Depends(get_repository_service_dep)
SecurityValidatorDep = Depends(get_security_validator_dep)