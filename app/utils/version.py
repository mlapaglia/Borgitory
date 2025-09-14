"""Version utilities for reading application version"""

import os
import logging

logger = logging.getLogger(__name__)


def get_version() -> str:
    """
    Get the application version
    
    Returns:
        str: The version string, or "Unknown" if unable to determine
    """
    env_version = os.getenv("BORGITORY_VERSION")
    if env_version and env_version.strip():
        return env_version.strip()

    return "Unknown"
