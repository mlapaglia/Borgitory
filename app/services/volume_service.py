import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class VolumeService:
    """Service to discover and manage mounted volumes"""

    async def get_mounted_volumes(self) -> List[str]:
        """Get list of mounted volumes by parsing mount information"""
        try:
            # Get mounted volumes using the provided command from debug service
            process = await asyncio.create_subprocess_shell(
                'mount | grep -v "^overlay\\|^proc\\|^tmpfs\\|^sysfs\\|^cgroup\\|^mqueue\\|^shm\\|^devpts" | grep " on /" | grep -v "/etc/\\|/proc\\|/sys\\|on / type" | awk \'{print $3}\'',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            mounted_volumes = []
            if process.returncode == 0 and stdout:
                # Parse the output to get mounted volumes
                volumes_output = stdout.decode().strip()
                if volumes_output:
                    mounted_volumes = [
                        line.strip()
                        for line in volumes_output.split("\n")
                        if line.strip()
                    ]

            # Filter out system directories and include commonly used backup paths
            filtered_volumes = []
            
            # Always include /repos if it exists (default backup location)
            import os
            if os.path.exists("/repos") and os.path.isdir("/repos"):
                filtered_volumes.append("/repos")
            
            # Add discovered volumes, filtering out system paths
            system_paths = {
                "/", "/boot", "/dev", "/etc", "/home", "/lib", "/lib64", 
                "/media", "/mnt", "/opt", "/proc", "/root", "/run", 
                "/sbin", "/srv", "/sys", "/tmp", "/usr", "/var"
            }
            
            for volume in mounted_volumes:
                # Skip system directories
                if volume in system_paths:
                    continue
                    
                # Skip paths that are clearly system-related
                if any(volume.startswith(f"{sys_path}/") for sys_path in system_paths):
                    continue
                    
                # Skip if path doesn't exist or isn't a directory
                if not os.path.exists(volume) or not os.path.isdir(volume):
                    continue
                    
                filtered_volumes.append(volume)

            # Remove duplicates while preserving order
            seen = set()
            unique_volumes = []
            for volume in filtered_volumes:
                if volume not in seen:
                    seen.add(volume)
                    unique_volumes.append(volume)

            logger.info(f"Discovered {len(unique_volumes)} mounted volumes: {unique_volumes}")
            return unique_volumes

        except Exception as e:
            logger.error(f"Error getting mounted volumes: {e}")
            # Fallback to just /repos if volume discovery fails
            import os
            if os.path.exists("/repos"):
                return ["/repos"]
            return []

    async def get_volume_info(self) -> Dict[str, Any]:
        """Get detailed information about mounted volumes"""
        try:
            mounted_volumes = await self.get_mounted_volumes()
            
            volume_info = {
                "mounted_volumes": mounted_volumes,
                "total_mounted_volumes": len(mounted_volumes),
                "accessible": True
            }
            
            return volume_info
            
        except Exception as e:
            logger.error(f"Error getting volume info: {e}")
            return {
                "error": str(e),
                "mounted_volumes": [],
                "total_mounted_volumes": 0,
                "accessible": False
            }


# Create a singleton instance
volume_service = VolumeService()