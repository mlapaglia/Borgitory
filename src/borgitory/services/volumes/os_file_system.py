import logging
import os
from typing import List

from borgitory.services.volumes.file_system_interface import FileSystemInterface

logger = logging.getLogger(__name__)


class OsFileSystem(FileSystemInterface):
    """Concrete filesystem implementation using os module"""

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def listdir(self, path: str) -> List[str]:
        return os.listdir(path)

    def join(self, *paths: str) -> str:
        return os.path.join(*paths)
