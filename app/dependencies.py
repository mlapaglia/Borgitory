"""
FastAPI dependency providers for the application.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.services.simple_command_runner import SimpleCommandRunner
from app.services.borg_service import BorgService
from app.services.job_service import JobService
from app.services.recovery_service import RecoveryService
from app.services.pushover_service import PushoverService
from app.services.job_stream_service import JobStreamService


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


@lru_cache()
def get_job_service() -> JobService:
    """
    Provide a JobService instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return JobService()


@lru_cache()
def get_recovery_service() -> RecoveryService:
    """
    Provide a RecoveryService instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return RecoveryService()


@lru_cache()
def get_pushover_service() -> PushoverService:
    """
    Provide a PushoverService instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return PushoverService()


@lru_cache()
def get_job_stream_service() -> JobStreamService:
    """
    Provide a JobStreamService instance with proper dependency injection.
    
    Using lru_cache ensures we get a singleton instance while
    still allowing for proper dependency injection and testing.
    """
    return JobStreamService()


# Type aliases for dependency injection
SimpleCommandRunnerDep = Annotated[
    SimpleCommandRunner, Depends(get_simple_command_runner)
]
BorgServiceDep = Annotated[BorgService, Depends(get_borg_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
RecoveryServiceDep = Annotated[RecoveryService, Depends(get_recovery_service)]
PushoverServiceDep = Annotated[PushoverService, Depends(get_pushover_service)]
JobStreamServiceDep = Annotated[JobStreamService, Depends(get_job_stream_service)]
