import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


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


class VolumeService:
    """Service to discover mounted volumes under /mnt"""

    def __init__(self, filesystem: FileSystemInterface = None):
        self.filesystem = filesystem or OsFileSystem()

    async def get_mounted_volumes(self) -> List[str]:
        """Get list of directories under /mnt (user-mounted volumes)"""
        try:
            mnt_path = "/mnt"
            mounted_volumes = []

            # Check if /mnt exists
            if not self.filesystem.exists(mnt_path) or not self.filesystem.is_dir(
                mnt_path
            ):
                logger.info("No /mnt directory found")
                return []

            # List all directories under /mnt
            for item in self.filesystem.listdir(mnt_path):
                item_path = self.filesystem.join(mnt_path, item)
                if self.filesystem.is_dir(item_path):
                    mounted_volumes.append(item_path)

            # Sort for consistent ordering
            mounted_volumes.sort()

            logger.info(
                f"Found {len(mounted_volumes)} mounted volumes under /mnt: {mounted_volumes}"
            )
            return mounted_volumes

        except Exception as e:
            logger.error(f"Error discovering mounted volumes under /mnt: {e}")
            return []

    async def get_volume_info(self) -> Dict[str, Any]:
        """Get detailed information about mounted volumes"""
        try:
            mounted_volumes = await self.get_mounted_volumes()

            volume_info = {
                "mounted_volumes": mounted_volumes,
                "total_mounted_volumes": len(mounted_volumes),
                "accessible": True,
            }

            return volume_info

        except Exception as e:
            logger.error(f"Error getting volume info: {e}")
            return {
                "error": str(e),
                "mounted_volumes": [],
                "total_mounted_volumes": 0,
                "accessible": False,
            }
