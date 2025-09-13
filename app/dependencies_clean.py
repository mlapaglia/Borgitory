"""
Clean FastAPI dependency injection following official documentation.

This implements the proper FastAPI DI pattern without global state,
making testing and maintenance much cleaner.
"""

from typing import Annotated
from fastapi import Depends

from app.services.interfaces import RepositoryQueryService, BorgServiceInterface, RepositoryService, SecurityValidator
from app.services.implementations import DefaultRepositoryQueryService, DefaultBorgService, DefaultRepositoryService, DefaultSecurityValidator
from app.services.simple_command_runner import SimpleCommandRunner


# Simple dependency functions (official FastAPI pattern)
def get_simple_command_runner() -> SimpleCommandRunner:
    """Get command runner instance."""
    return SimpleCommandRunner()


def get_repository_query_service() -> RepositoryQueryService:
    """Get repository query service instance."""
    return DefaultRepositoryQueryService()


def get_clean_security_validator() -> SecurityValidator:
    """Get security validator instance."""
    return DefaultSecurityValidator()


def get_clean_borg_service(
    command_runner: Annotated[SimpleCommandRunner, Depends(get_simple_command_runner)]
) -> BorgServiceInterface:
    """Get Borg service instance using clean DI pattern."""
    from app.services.borg_service import BorgService
    return BorgService(command_runner=command_runner)


def get_clean_repository_service(
    security: Annotated[SecurityValidator, Depends(get_clean_security_validator)],
    borg: Annotated[BorgServiceInterface, Depends(get_clean_borg_service)]
) -> RepositoryService:
    """Get repository service with clean FastAPI DI chaining."""
    return DefaultRepositoryService(security, borg)


# Type aliases for clean endpoint signatures (official FastAPI pattern)
RepositoryQueryDep = Annotated[RepositoryQueryService, Depends(get_repository_query_service)]
CleanBorgServiceDep = Annotated[BorgServiceInterface, Depends(get_clean_borg_service)]
CleanRepositoryServiceDep = Annotated[RepositoryService, Depends(get_clean_repository_service)]
CleanSecurityValidatorDep = Annotated[SecurityValidator, Depends(get_clean_security_validator)]