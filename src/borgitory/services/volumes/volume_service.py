import logging
from typing import List, Optional, TypedDict

from borgitory.services.volumes.file_system_interface import FileSystemInterface
from borgitory.services.volumes.os_file_system import OsFileSystem

logger = logging.getLogger(__name__)


class VolumeInfo(TypedDict, total=False):
    """Volume information structure"""

    # Success fields
    mounted_volumes: List[str]
    total_mounted_volumes: int
    accessible: bool
    # Error field
    error: str


class VolumeService:
    """Service to discover mounted volumes under /mnt"""

    def __init__(self, filesystem: Optional[FileSystemInterface] = None) -> None:
        self.filesystem = filesystem or OsFileSystem()

    async def get_mounted_volumes(self) -> List[str]:
        """Get list of directories under /mnt (user-mounted volumes)"""
        try:
            mnt_path = "/mnt"
            mounted_volumes = []

            if not self.filesystem.exists(mnt_path) or not self.filesystem.is_dir(
                mnt_path
            ):
                logger.info("No /mnt directory found")
                return []

            for item in self.filesystem.listdir(mnt_path):
                item_path = self.filesystem.join(mnt_path, item)
                if self.filesystem.is_dir(item_path):
                    mounted_volumes.append(item_path)

            mounted_volumes.sort()

            logger.info(
                f"Found {len(mounted_volumes)} mounted volumes under /mnt: {mounted_volumes}"
            )
            return mounted_volumes

        except Exception as e:
            logger.error(f"Error discovering mounted volumes under /mnt: {e}")
            return []

    async def get_volume_info(self) -> VolumeInfo:
        """Get detailed information about mounted volumes"""
        try:
            mounted_volumes = await self.get_mounted_volumes()

            volume_info: VolumeInfo = {
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
