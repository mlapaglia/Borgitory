"""
WSL services package for Windows Subsystem for Linux integration.

This package provides services for detecting WSL availability,
executing commands through WSL, and handling path translations
between Windows and WSL environments.
"""

from .wsl_detection_service import (
    WSLDetectionService,
    WSLEnvironmentInfo,
    WSLDistribution,
    get_wsl_detection_service,
)

__all__ = [
    "WSLDetectionService",
    "WSLEnvironmentInfo",
    "WSLDistribution",
    "get_wsl_detection_service",
]
