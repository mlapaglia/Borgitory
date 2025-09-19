"""
Protocol interfaces for Borgitory services.

This module defines protocol interfaces that enable proper dependency injection,
testing, and loose coupling between services.
"""

from .command_runner import CommandRunner, CommandResult
from .storage_service import StorageService
from .job_manager import JobManager, JobExecutor
from .volume_service import VolumeService
from .borg_service import BorgService

__all__ = [
    "CommandRunner",
    "CommandResult",
    "StorageService",
    "JobManager",
    "JobExecutor",
    "VolumeService",
    "BorgService",
]
