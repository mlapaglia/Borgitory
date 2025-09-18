"""
Volume service protocol interface.

Defines the contract for volume and filesystem services.
"""

from typing import Protocol, List, Dict, Any


class VolumeService(Protocol):
    """Protocol for volume and filesystem services"""
    
    async def get_mounted_volumes(self) -> List[str]:
        """
        Get list of mounted volume paths.
        
        Returns:
            List of mounted volume paths
        """
        ...
    
    async def get_volume_info(self) -> Dict[str, Any]:
        """
        Get information about available volumes.
        
        Returns:
            Dictionary with volume information
        """
        ...
