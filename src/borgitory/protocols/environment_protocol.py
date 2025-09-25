"""
Environment Protocol - Abstraction for environment and system operations
"""

from datetime import datetime
from typing import Optional, Protocol


class EnvironmentProtocol(Protocol):
    """Protocol for environment and system operations"""

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable"""
        ...

    def get_cwd(self) -> str:
        """Get current working directory"""
        ...

    def now_utc(self) -> datetime:
        """Get current UTC datetime"""
        ...

    def get_database_url(self) -> str:
        """Get database URL"""
        ...


class DefaultEnvironment:
    """Default implementation of EnvironmentProtocol"""

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable"""
        import os

        return os.getenv(key, default)

    def get_cwd(self) -> str:
        """Get current working directory"""
        import os

        return os.getcwd()

    def now_utc(self) -> datetime:
        """Get current UTC datetime"""
        from borgitory.utils.datetime_utils import now_utc

        return now_utc()

    def get_database_url(self) -> str:
        """Get database URL"""
        from borgitory.config_module import DATABASE_URL

        return DATABASE_URL
