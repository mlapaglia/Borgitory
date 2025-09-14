from abc import ABC, abstractmethod
from typing import List


class FileSystemInterface(ABC):
    """Abstract interface for filesystem operations"""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists"""
        pass

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Check if path is a directory"""
        pass

    @abstractmethod
    def listdir(self, path: str) -> List[str]:
        """List contents of directory"""
        pass

    @abstractmethod
    def join(self, *paths: str) -> str:
        """Join path components"""
        pass
