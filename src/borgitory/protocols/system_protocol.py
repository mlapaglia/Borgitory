"""
System operations protocol for abstracting OS and import operations.

This protocol defines the interface for system operations that need to be
abstracted for testing and cross-platform compatibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class SystemOperationsProtocol(ABC):
    """Protocol for system operations like file system, imports, and subprocess."""

    @abstractmethod
    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """Create directories recursively."""
        pass

    @abstractmethod
    def path_exists(self, path: str) -> bool:
        """Check if a path exists."""
        pass

    @abstractmethod
    def get_data_dir(self) -> str:
        """Get the application data directory."""
        pass

    @abstractmethod
    def import_resources(self) -> Any:
        """Import importlib.resources module."""
        pass

    @abstractmethod
    def resources_files(self, package: str) -> Any:
        """Get package files using importlib.resources."""
        pass

    @abstractmethod
    def path_truediv(self, base_path: Any, sub_path: str) -> Any:
        """Perform path / operation."""
        pass

    @abstractmethod
    def path_str(self, path: Any) -> str:
        """Convert path to string."""
        pass

    @abstractmethod
    def path_is_file(self, path: Any) -> bool:
        """Check if path is a file."""
        pass


class DatabaseOperationsProtocol(ABC):
    """Protocol for database operations."""

    @abstractmethod
    def get_current_revision(self) -> Optional[str]:
        """Get the current database revision."""
        pass


class MigrationOperationsProtocol(ABC):
    """Protocol for migration operations."""

    @abstractmethod
    def run_alembic_upgrade(self, config_path: str) -> bool:
        """Run alembic upgrade command."""
        pass
