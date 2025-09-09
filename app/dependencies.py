"""
FastAPI dependency providers for the application.
"""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.services.simple_command_runner import SimpleCommandRunner
from app.services.borg_service import BorgService


@lru_cache()
def get_simple_command_runner() -> SimpleCommandRunner:
    """
    Provide a SimpleCommandRunner instance.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return SimpleCommandRunner()


@lru_cache()
def get_borg_service() -> BorgService:
    """
    Provide a BorgService instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return BorgService(command_runner=get_simple_command_runner())


# Type aliases for dependency injection
SimpleCommandRunnerDep = Annotated[SimpleCommandRunner, Depends(get_simple_command_runner)]
BorgServiceDep = Annotated[BorgService, Depends(get_borg_service)]