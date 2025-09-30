"""
WSL Detection Service for checking WSL availability and configuration.

This service determines if WSL is available on the current Windows system
and validates the WSL environment for Borgitory operations.
"""

import asyncio
import logging
import platform
import re
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WSLDistribution:
    """Information about a WSL distribution."""

    name: str
    version: str
    is_default: bool
    state: str  # "Running", "Stopped", etc.


@dataclass
class WSLEnvironmentInfo:
    """Complete WSL environment information."""

    wsl_available: bool
    wsl_version: Optional[str]
    distributions: List[WSLDistribution]
    default_distribution: Optional[str]
    borg_available: bool
    borg_version: Optional[str]
    mount_accessible: bool
    error_message: Optional[str]


class WSLDetectionService:
    """Service for detecting and validating WSL environment."""

    def __init__(self) -> None:
        self._cached_info: Optional[WSLEnvironmentInfo] = None
        self._cache_valid = False

    async def get_wsl_info(self, force_refresh: bool = False) -> WSLEnvironmentInfo:
        """
        Get comprehensive WSL environment information.

        Args:
            force_refresh: Force refresh of cached information

        Returns:
            WSLEnvironmentInfo with complete WSL status
        """
        if not force_refresh and self._cache_valid and self._cached_info:
            return self._cached_info

        logger.info("Detecting WSL environment...")

        try:
            if platform.system().lower() != "windows":
                info = WSLEnvironmentInfo(
                    wsl_available=False,
                    wsl_version=None,
                    distributions=[],
                    default_distribution=None,
                    borg_available=False,
                    borg_version=None,
                    mount_accessible=False,
                    error_message="WSL is only available on Windows",
                )
                self._cached_info = info
                self._cache_valid = True
                return info

            wsl_available, wsl_version, error_msg = await self._check_wsl_availability()

            if not wsl_available:
                info = WSLEnvironmentInfo(
                    wsl_available=False,
                    wsl_version=None,
                    distributions=[],
                    default_distribution=None,
                    borg_available=False,
                    borg_version=None,
                    mount_accessible=False,
                    error_message=error_msg,
                )
                self._cached_info = info
                self._cache_valid = True
                return info

            # Get WSL distributions
            distributions = await self._get_wsl_distributions()
            default_distro = self._find_default_distribution(distributions)

            # Check borg availability in WSL
            borg_available, borg_version = await self._check_borg_in_wsl()

            # Check if Windows filesystem is accessible from WSL
            mount_accessible = await self._check_mount_accessibility()

            info = WSLEnvironmentInfo(
                wsl_available=wsl_available,
                wsl_version=wsl_version,
                distributions=distributions,
                default_distribution=default_distro,
                borg_available=borg_available,
                borg_version=borg_version,
                mount_accessible=mount_accessible,
                error_message=None,
            )

            self._cached_info = info
            self._cache_valid = True
            logger.info(
                f"WSL detection complete: WSL={wsl_available}, Borg={borg_available}, Default={default_distro}"
            )
            return info

        except Exception as e:
            logger.error(f"Error during WSL detection: {e}")
            info = WSLEnvironmentInfo(
                wsl_available=False,
                wsl_version=None,
                distributions=[],
                default_distribution=None,
                borg_available=False,
                borg_version=None,
                mount_accessible=False,
                error_message=f"WSL detection failed: {str(e)}",
            )
            self._cached_info = info
            self._cache_valid = True
            return info

    async def is_wsl_available(self) -> bool:
        """Quick check if WSL is available."""
        info = await self.get_wsl_info()
        return info.wsl_available

    async def is_borg_available_in_wsl(self) -> bool:
        """Quick check if borg is available in WSL."""
        info = await self.get_wsl_info()
        return info.borg_available

    async def get_recommended_setup_instructions(self) -> List[str]:
        """Get setup instructions based on current WSL state."""
        info = await self.get_wsl_info()
        instructions = []

        if not info.wsl_available:
            instructions.extend(
                [
                    "WSL is not available on this system.",
                    "1. Enable WSL feature: dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart",
                    "2. Enable Virtual Machine Platform: dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart",
                    "3. Restart your computer",
                    "4. Install WSL 2: wsl --install",
                    "5. Install a Linux distribution from Microsoft Store (Ubuntu recommended)",
                ]
            )
        elif not info.distributions:
            instructions.extend(
                [
                    "WSL is available but no distributions are installed.",
                    "1. Install a Linux distribution: wsl --install -d Ubuntu",
                    "2. Set up your Linux user account when prompted",
                ]
            )
        elif not info.borg_available:
            instructions.extend(
                [
                    "WSL is available but BorgBackup is not installed.",
                    "1. Open WSL terminal: wsl",
                    "2. Update package list: sudo apt update",
                    "3. Install BorgBackup: sudo apt install borgbackup",
                    "4. Verify installation: borg --version",
                ]
            )

        if info.wsl_available and not info.mount_accessible:
            instructions.append(
                "Warning: Windows filesystem may not be accessible from WSL"
            )

        return instructions

    async def _check_wsl_availability(
        self,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check if WSL is available and get version."""
        try:
            # Try to get WSL version
            process = await asyncio.create_subprocess_exec(
                "wsl",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

            if process.returncode == 0:
                version_output = stdout.decode().strip()
                # Extract WSL version from output
                version_match = re.search(r"WSL version: ([\d.]+)", version_output)
                version = version_match.group(1) if version_match else "Unknown"
                return True, version, None
            else:
                error_msg = stderr.decode().strip()
                logger.warning(f"WSL version check failed: {error_msg}")
                return False, None, f"WSL not available: {error_msg}"

        except asyncio.TimeoutError:
            return False, None, "WSL command timed out"
        except FileNotFoundError:
            return False, None, "WSL command not found"
        except Exception as e:
            return False, None, f"WSL availability check failed: {str(e)}"

    async def _get_wsl_distributions(self) -> List[WSLDistribution]:
        """Get list of installed WSL distributions."""
        try:
            process = await asyncio.create_subprocess_exec(
                "wsl",
                "--list",
                "--verbose",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

            if process.returncode != 0:
                logger.warning(f"Failed to list WSL distributions: {stderr.decode()}")
                return []

            distributions = []
            output = stdout.decode("utf-16le" if b"\x00" in stdout else "utf-8").strip()
            lines = output.split("\n")

            # Skip header line
            for line in lines[1:]:
                if not line.strip():
                    continue

                # Parse distribution info
                # WSL output sometimes has Unicode formatting issues
                line_clean = line.strip()
                is_default = "*" in line_clean

                # Remove the * and extra spaces, handle spaced characters
                line_clean = line_clean.replace("*", "").strip()

                # WSL sometimes outputs with spaces between characters, remove them
                if (
                    " " in line_clean
                    and len(line_clean.replace(" ", "")) < len(line_clean) // 2
                ):
                    line_clean = line_clean.replace(" ", "")

                # Split by multiple spaces to get parts
                parts = [
                    part for part in re.split(r"\s{2,}", line_clean) if part.strip()
                ]

                if len(parts) >= 3:
                    name = parts[0].strip()
                    state = parts[1].strip()
                    version = parts[2].strip()

                    distributions.append(
                        WSLDistribution(
                            name=name,
                            version=version,
                            is_default=is_default,
                            state=state,
                        )
                    )

            return distributions

        except (asyncio.TimeoutError, FileNotFoundError, Exception) as e:
            logger.warning(f"Failed to get WSL distributions: {e}")
            return []

    def _find_default_distribution(
        self, distributions: List[WSLDistribution]
    ) -> Optional[str]:
        """Find the default WSL distribution."""
        for dist in distributions:
            if dist.is_default:
                return dist.name

        # If no default found but distributions exist, return the first one
        if distributions:
            return distributions[0].name

        return None

    async def _check_borg_in_wsl(self) -> tuple[bool, Optional[str]]:
        """Check if borg is available in WSL."""
        try:
            process = await asyncio.create_subprocess_exec(
                "wsl",
                "borg",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

            if process.returncode == 0:
                version_output = stdout.decode().strip()
                # Extract version number
                version_match = re.search(r"borg ([\d.]+)", version_output)
                version = version_match.group(1) if version_match else version_output
                return True, version
            else:
                return False, None

        except (asyncio.TimeoutError, FileNotFoundError, Exception) as e:
            logger.debug(f"Borg availability check failed: {e}")
            return False, None

    async def _check_mount_accessibility(self) -> bool:
        """Check if Windows filesystem is accessible from WSL."""
        try:
            # Try to access C: drive through WSL
            process = await asyncio.create_subprocess_exec(
                "wsl",
                "test",
                "-d",
                "/mnt/c",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=5.0)

            return process.returncode == 0

        except (asyncio.TimeoutError, FileNotFoundError, Exception) as e:
            logger.debug(f"Mount accessibility check failed: {e}")
            return False

    def invalidate_cache(self) -> None:
        """Invalidate cached WSL information."""
        self._cache_valid = False
        self._cached_info = None


# Global instance for easy access
_wsl_detection_service: Optional[WSLDetectionService] = None


def get_wsl_detection_service() -> WSLDetectionService:
    """Get the global WSL detection service instance."""
    global _wsl_detection_service
    if _wsl_detection_service is None:
        _wsl_detection_service = WSLDetectionService()
    return _wsl_detection_service
