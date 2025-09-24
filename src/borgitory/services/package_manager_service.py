"""
Package Manager Service for installing Debian packages in the container.
Tracks user-installed packages in the database for persistence across container restarts.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from borgitory.protocols.command_protocols import CommandRunnerProtocol
from borgitory.models.database import UserInstalledPackage
from borgitory.utils.datetime_utils import now_utc

logger = logging.getLogger(__name__)


@dataclass
class PackageInfo:
    """Information about a Debian package."""

    name: str
    version: str
    description: str
    section: str
    installed: bool = False
    user_installed: bool = False


class PackageManagerService:
    """Service for managing Debian packages in the container."""

    def __init__(
        self,
        command_runner: CommandRunnerProtocol,
        db_session: Optional[Session] = None,
    ):
        self.command_runner = command_runner
        self.db_session = db_session
        self._package_cache: Dict[str, PackageInfo] = {}
        self._cache_updated = False

    async def search_packages(self, query: str, limit: int = 50) -> List[PackageInfo]:
        """Search for packages matching the query."""
        await self._ensure_cache_updated()

        query_lower = query.lower()
        matching_packages = []

        for package in self._package_cache.values():
            if package.name.lower().startswith(query_lower):
                matching_packages.append(package)

                if len(matching_packages) >= limit:
                    break

        matching_packages.sort(key=lambda p: p.name.lower())

        return matching_packages[:limit]

    async def get_package_info(self, package_name: str) -> Optional[PackageInfo]:
        """Get detailed information about a specific package."""
        self._validate_package_name(package_name)

        try:
            result = await self.command_runner.run_command(
                ["apt-cache", "show", package_name], timeout=10
            )

            if result.return_code != 0:
                return None

            package_info = self._parse_package_info(result.stdout)
            if package_info:
                installed_result = await self.command_runner.run_command(
                    ["dpkg", "-l", package_name], timeout=5
                )
                package_info.installed = installed_result.return_code == 0

            return package_info

        except Exception as e:
            logger.error(f"Error getting package info for {package_name}: {e}")
            return None

    async def install_packages(self, packages: List[str]) -> Tuple[bool, str]:
        """Install packages using apt-get."""
        validated_packages = self._validate_package_names(packages)

        try:
            update_result = await self.command_runner.run_command(
                ["apt-get", "update"], timeout=120
            )

            if update_result.return_code != 0:
                return False, f"Failed to update package cache: {update_result.stderr}"

            install_result = await self.command_runner.run_command(
                ["apt-get", "install", "-y", "--no-install-recommends"]
                + validated_packages,
                timeout=300,
            )

            if install_result.return_code == 0:
                self._cache_updated = False

                install_command = f"apt-get install {' '.join(validated_packages)}"
                for package_name in validated_packages:
                    package_info = await self.get_package_info(package_name)
                    if package_info and package_info.installed:
                        self._save_installed_package(
                            package_name=package_name,
                            version=package_info.version,
                            install_command=install_command,
                        )

                return True, f"Successfully installed: {', '.join(validated_packages)}"
            else:
                error_msg = install_result.stderr or install_result.stdout
                return False, f"Installation failed: {error_msg}"

        except Exception as e:
            logger.error(f"Error installing packages {packages}: {e}")
            return False, f"Installation error: {str(e)}"

    async def remove_packages(self, packages: List[str]) -> Tuple[bool, str]:
        """Remove packages using apt-get."""
        validated_packages = self._validate_package_names(packages)

        try:
            result = await self.command_runner.run_command(
                ["apt-get", "remove", "-y"] + validated_packages, timeout=120
            )

            if result.return_code == 0:
                self._cache_updated = False

                for package_name in validated_packages:
                    self._remove_installed_package(package_name)

                return True, f"Successfully removed: {', '.join(validated_packages)}"
            else:
                error_msg = result.stderr or result.stdout
                return False, f"Removal failed: {error_msg}"

        except Exception as e:
            logger.error(f"Error removing packages {packages}: {e}")
            return False, f"Removal error: {str(e)}"

    async def list_installed_packages(self) -> List[PackageInfo]:
        """List all installed packages."""
        try:
            result = await self.command_runner.run_command(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"],
                timeout=30,
            )

            if result.return_code != 0:
                return []

            installed_packages = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) >= 3 and "installed" in parts[2]:
                    package_info = PackageInfo(
                        name=parts[0],
                        version=parts[1],
                        description="",  # Would need separate query for description
                        section="",
                        installed=True,
                    )
                    installed_packages.append(package_info)

            return installed_packages

        except Exception as e:
            logger.error(f"Error listing installed packages: {e}")
            return []

    async def _ensure_cache_updated(self) -> None:
        """Ensure the package cache is updated."""
        if self._cache_updated:
            return

        try:
            update_result = await self.command_runner.run_command(
                ["apt-get", "update"], timeout=60
            )

            if update_result.return_code != 0:
                logger.warning(f"apt update failed: {update_result.stderr}")

            result = await self.command_runner.run_command(
                ["apt-cache", "search", "."], timeout=30
            )

            if result.return_code == 0:
                self._package_cache = {}
                for line in result.stdout.strip().split("\n"):
                    if " - " in line:
                        name, description = line.split(" - ", 1)
                        package_info = PackageInfo(
                            name=name.strip(),
                            version="",  # Version would need separate query
                            description=description.strip(),
                            section="",
                        )
                        self._package_cache[name.strip()] = package_info

                self._cache_updated = True
                logger.info(
                    f"Updated package cache with {len(self._package_cache)} packages"
                )

        except Exception as e:
            logger.error(f"Error updating package cache: {e}")

    def _validate_package_names(self, packages: List[str]) -> List[str]:
        """Validate package names to prevent injection attacks."""
        validated_packages = []
        for pkg in packages:
            self._validate_package_name(pkg)
            validated_packages.append(pkg)
        return validated_packages

    def _validate_package_name(self, package_name: str) -> None:
        """Validate a single package name."""
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9+\-\.]+$", package_name):
            raise ValueError(f"Invalid package name: {package_name}")

        if len(package_name) > 100:
            raise ValueError(f"Package name too long: {package_name}")

    def _parse_package_info(self, apt_cache_output: str) -> Optional[PackageInfo]:
        """Parse apt-cache show output into PackageInfo."""
        try:
            lines = apt_cache_output.strip().split("\n")
            package_data = {}

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    package_data[key.strip()] = value.strip()

            if "Package" in package_data:
                return PackageInfo(
                    name=package_data.get("Package", ""),
                    version=package_data.get("Version", ""),
                    description=package_data.get("Description", ""),
                    section=package_data.get("Section", ""),
                )

        except Exception as e:
            logger.error(f"Error parsing package info: {e}")

        return None

    def _save_installed_package(
        self,
        package_name: str,
        version: str,
        install_command: str,
        dependencies: Optional[List[str]] = None,
    ) -> None:
        """Save installed package to database for persistence."""
        if not self.db_session:
            logger.warning(
                "No database session available, cannot track installed package"
            )
            return

        try:
            existing = (
                self.db_session.query(UserInstalledPackage)
                .filter(UserInstalledPackage.package_name == package_name)
                .first()
            )

            if existing:
                existing.version = version
                existing.installed_at = now_utc()
                existing.install_command = install_command
                existing.dependencies_installed = (
                    json.dumps(dependencies) if dependencies else None
                )
            else:
                package_record = UserInstalledPackage()
                package_record.package_name = package_name
                package_record.version = version
                package_record.installed_at = now_utc()
                package_record.install_command = install_command
                package_record.dependencies_installed = (
                    json.dumps(dependencies) if dependencies else None
                )
                self.db_session.add(package_record)

            self.db_session.commit()
            logger.info(
                f"Tracked installation of package {package_name} v{version} in database"
            )

        except Exception as e:
            logger.error(
                f"Failed to save installed package {package_name} to database: {e}"
            )
            if self.db_session:
                self.db_session.rollback()

    def _remove_installed_package(self, package_name: str) -> None:
        """Remove installed package record from database."""
        if not self.db_session:
            logger.warning(
                "No database session available, cannot remove tracked package"
            )
            return

        try:
            package_record = (
                self.db_session.query(UserInstalledPackage)
                .filter(UserInstalledPackage.package_name == package_name)
                .first()
            )

            if package_record:
                self.db_session.delete(package_record)
                self.db_session.commit()
                logger.info(f"Removed package {package_name} from database tracking")

        except Exception as e:
            logger.error(f"Failed to remove package {package_name} from database: {e}")
            if self.db_session:
                self.db_session.rollback()

    def get_user_installed_packages(self) -> List[UserInstalledPackage]:
        """Get list of user-installed packages from database."""
        if not self.db_session:
            return []

        try:
            return (
                self.db_session.query(UserInstalledPackage)
                .order_by(UserInstalledPackage.installed_at.desc())
                .all()
            )
        except Exception as e:
            logger.error(f"Failed to get user-installed packages from database: {e}")
            return []

    async def ensure_user_packages_installed(self) -> Tuple[bool, str]:
        """Ensure all user-installed packages from database are actually installed.
        This is called on startup to restore packages after container restart."""
        user_packages = self.get_user_installed_packages()

        if not user_packages:
            logger.info("No user-installed packages to restore")
            return True, "No packages to restore"

        missing_packages = []

        for package_record in user_packages:
            package_info = await self.get_package_info(package_record.package_name)
            if not package_info or not package_info.installed:
                missing_packages.append(package_record.package_name)

        if not missing_packages:
            logger.info(f"All {len(user_packages)} user packages are already installed")
            return True, f"All {len(user_packages)} packages already installed"

        logger.info(
            f"Reinstalling {len(missing_packages)} missing packages: {', '.join(missing_packages)}"
        )

        success, message = await self.install_packages(missing_packages)

        if success:
            logger.info(f"Successfully restored {len(missing_packages)} packages")
            return (
                True,
                f"Restored {len(missing_packages)} packages: {', '.join(missing_packages)}",
            )
        else:
            logger.error(f"Failed to restore some packages: {message}")
            return False, f"Failed to restore packages: {message}"
