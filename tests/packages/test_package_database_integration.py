"""
Tests for PackageManagerService database integration and startup restoration
"""

import pytest
from typing import Any, Dict, List, Optional, Generator
from unittest.mock import AsyncMock, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from borgitory.services.package_manager_service import PackageManagerService
from borgitory.services.startup.package_restoration_service import (
    PackageRestorationService,
)
from borgitory.models.database import Base, UserInstalledPackage
from borgitory.protocols.command_protocols import CommandResult
from borgitory.utils.datetime_utils import now_utc


class MockCommandRunner:
    """Mock command runner for testing"""

    def __init__(self) -> None:
        self._run_command_mock = AsyncMock()

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        **kwargs: Any,
    ) -> CommandResult:
        result = await self._run_command_mock(
            command, env=env, timeout=timeout, **kwargs
        )
        return result  # type: ignore[no-any-return]


@pytest.fixture
def in_memory_db() -> Any:
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal


@pytest.fixture
def db_session(in_memory_db: Any) -> Generator[Session, None, None]:
    """Create a database session for testing"""
    session = in_memory_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_command_runner() -> MockCommandRunner:
    return MockCommandRunner()


@pytest.fixture
def package_service_with_db(
    mock_command_runner: MockCommandRunner, db_session: Session
) -> PackageManagerService:
    return PackageManagerService(
        command_runner=mock_command_runner, db_session=db_session
    )


@pytest.mark.asyncio
class TestPackageManagerDatabaseIntegration:
    async def test_install_package_saves_to_database(
        self,
        package_service_with_db: PackageManagerService,
        mock_command_runner: MockCommandRunner,
        db_session: Session,
    ) -> None:
        """Test that installing a package saves it to the database"""
        # Mock successful installation
        mock_command_runner._run_command_mock.side_effect = [
            CommandResult(  # apt-get update
                success=True,
                return_code=0,
                stdout="Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease\n",
                stderr="",
                duration=2.0,
            ),
            CommandResult(  # apt-get install
                success=True,
                return_code=0,
                stdout="Reading package lists...\nThe following NEW packages will be installed:\n  curl\n",
                stderr="",
                duration=5.0,
            ),
            CommandResult(  # apt-cache show (for version info)
                success=True,
                return_code=0,
                stdout="Package: curl\nVersion: 7.81.0-1ubuntu1.15\nDescription: command line tool\nSection: web\n",
                stderr="",
                duration=0.1,
            ),
            CommandResult(  # dpkg -l (check installed)
                success=True,
                return_code=0,
                stdout="ii  curl 7.81.0-1ubuntu1.15 amd64",
                stderr="",
                duration=0.1,
            ),
        ]

        # Install package
        success, message = await package_service_with_db.install_packages(["curl"])

        assert success is True
        assert "Successfully installed: curl" in message

        # Check database record was created
        package_record = (
            db_session.query(UserInstalledPackage)
            .filter(UserInstalledPackage.package_name == "curl")
            .first()
        )

        assert package_record is not None
        assert package_record.package_name == "curl"
        assert package_record.version == "7.81.0-1ubuntu1.15"
        assert package_record.install_command == "apt-get install curl"
        assert package_record.installed_at is not None

    async def test_remove_package_removes_from_database(
        self,
        package_service_with_db: PackageManagerService,
        mock_command_runner: MockCommandRunner,
        db_session: Session,
    ) -> None:
        """Test that removing a package removes it from the database"""
        # First create a package record in database
        package_record = UserInstalledPackage()
        package_record.package_name = "curl"
        package_record.version = "7.81.0-1ubuntu1.15"
        package_record.installed_at = now_utc()
        package_record.install_command = "apt-get install curl"
        db_session.add(package_record)
        db_session.commit()

        # Mock successful removal
        mock_command_runner._run_command_mock.return_value = CommandResult(
            success=True,
            return_code=0,
            stdout="Reading package lists...\nThe following packages will be REMOVED:\n  curl\n",
            stderr="",
            duration=3.0,
        )

        # Remove package
        success, message = await package_service_with_db.remove_packages(["curl"])

        assert success is True
        assert "Successfully removed: curl" in message

        # Check database record was removed
        remaining_record = (
            db_session.query(UserInstalledPackage)
            .filter(UserInstalledPackage.package_name == "curl")
            .first()
        )

        assert remaining_record is None

    async def test_get_user_installed_packages(
        self, package_service_with_db: PackageManagerService, db_session: Session
    ) -> None:
        """Test getting user-installed packages from database"""
        # Create test package records
        package1 = UserInstalledPackage()
        package1.package_name = "curl"
        package1.version = "7.81.0-1ubuntu1.15"
        package1.installed_at = now_utc()
        package1.install_command = "apt-get install curl"

        package2 = UserInstalledPackage()
        package2.package_name = "jq"
        package2.version = "1.6-2.1ubuntu3"
        package2.installed_at = now_utc()
        package2.install_command = "apt-get install jq"

        packages = [package1, package2]

        for pkg in packages:
            db_session.add(pkg)
        db_session.commit()

        # Get user packages
        user_packages = package_service_with_db.get_user_installed_packages()

        assert len(user_packages) == 2
        package_names = [pkg.package_name for pkg in user_packages]
        assert "curl" in package_names
        assert "jq" in package_names

    async def test_ensure_user_packages_installed_no_missing(
        self,
        package_service_with_db: PackageManagerService,
        mock_command_runner: MockCommandRunner,
        db_session: Session,
    ) -> None:
        """Test ensure_user_packages_installed when all packages are already installed"""
        # Create package record in database
        package_record = UserInstalledPackage()
        package_record.package_name = "curl"
        package_record.version = "7.81.0-1ubuntu1.15"
        package_record.installed_at = now_utc()
        package_record.install_command = "apt-get install curl"
        db_session.add(package_record)
        db_session.commit()

        # Mock package info showing it's installed
        mock_command_runner._run_command_mock.side_effect = [
            CommandResult(  # apt-cache show
                success=True,
                return_code=0,
                stdout="Package: curl\nVersion: 7.81.0-1ubuntu1.15\nDescription: command line tool\nSection: web\n",
                stderr="",
                duration=0.1,
            ),
            CommandResult(  # dpkg -l (check installed)
                success=True,
                return_code=0,
                stdout="ii  curl 7.81.0-1ubuntu1.15 amd64",
                stderr="",
                duration=0.1,
            ),
        ]

        (
            success,
            message,
        ) = await package_service_with_db.ensure_user_packages_installed()

        assert success is True
        assert "already installed" in message.lower()

        # Should only have called get_package_info, not install
        assert mock_command_runner._run_command_mock.call_count == 2

    async def test_ensure_user_packages_installed_with_missing(
        self,
        package_service_with_db: PackageManagerService,
        mock_command_runner: MockCommandRunner,
        db_session: Session,
    ) -> None:
        """Test ensure_user_packages_installed when packages need to be reinstalled"""
        # Create package record in database
        package_record = UserInstalledPackage()
        package_record.package_name = "curl"
        package_record.version = "7.81.0-1ubuntu1.15"
        package_record.installed_at = now_utc()
        package_record.install_command = "apt-get install curl"
        db_session.add(package_record)
        db_session.commit()

        # Mock package info showing it's NOT installed, then successful reinstall
        mock_command_runner._run_command_mock.side_effect = [
            # First call: get_package_info (not installed)
            CommandResult(  # apt-cache show
                success=True,
                return_code=0,
                stdout="Package: curl\nVersion: 7.81.0-1ubuntu1.15\nDescription: command line tool\nSection: web\n",
                stderr="",
                duration=0.1,
            ),
            CommandResult(  # dpkg -l (not installed)
                success=False, return_code=1, stdout="", stderr="", duration=0.1
            ),
            # Then install_packages calls
            CommandResult(  # apt-get update
                success=True,
                return_code=0,
                stdout="Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease\n",
                stderr="",
                duration=2.0,
            ),
            CommandResult(  # apt-get install
                success=True,
                return_code=0,
                stdout="Reading package lists...\nThe following NEW packages will be installed:\n  curl\n",
                stderr="",
                duration=5.0,
            ),
            # Then get_package_info again (for version tracking)
            CommandResult(  # apt-cache show
                success=True,
                return_code=0,
                stdout="Package: curl\nVersion: 7.81.0-1ubuntu1.15\nDescription: command line tool\nSection: web\n",
                stderr="",
                duration=0.1,
            ),
            CommandResult(  # dpkg -l (now installed)
                success=True,
                return_code=0,
                stdout="ii  curl 7.81.0-1ubuntu1.15 amd64",
                stderr="",
                duration=0.1,
            ),
        ]

        (
            success,
            message,
        ) = await package_service_with_db.ensure_user_packages_installed()

        assert success is True
        assert "Restored 1 packages: curl" in message

        # Should have called get_package_info, then install, then get_package_info again
        assert mock_command_runner._run_command_mock.call_count == 6


@pytest.mark.asyncio
class TestPackageRestorationService:
    async def test_restore_user_packages_success(self, in_memory_db: Any) -> None:
        """Test successful package restoration on startup"""
        db_session = in_memory_db()

        # Create package record in database
        package_record = UserInstalledPackage()
        package_record.package_name = "curl"
        package_record.version = "7.81.0-1ubuntu1.15"
        package_record.installed_at = now_utc()
        package_record.install_command = "apt-get install curl"
        db_session.add(package_record)
        db_session.commit()

        # Create mock package manager
        mock_package_manager = Mock(spec=PackageManagerService)
        mock_package_manager.ensure_user_packages_installed = AsyncMock(
            return_value=(True, "Restored 1 packages: curl")
        )

        # Create restoration service with injected package manager
        restoration_service = PackageRestorationService(
            package_manager=mock_package_manager
        )

        # Test restoration
        await restoration_service.restore_user_packages()

        # Verify the method was called
        mock_package_manager.ensure_user_packages_installed.assert_called_once()

        db_session.close()

    async def test_restore_user_packages_failure(self, in_memory_db: Any) -> None:
        """Test package restoration failure handling"""
        db_session = in_memory_db()

        # Create mock package manager that fails
        mock_package_manager = Mock(spec=PackageManagerService)
        mock_package_manager.ensure_user_packages_installed = AsyncMock(
            return_value=(False, "Installation failed: Package not found")
        )

        # Create restoration service with injected package manager
        restoration_service = PackageRestorationService(
            package_manager=mock_package_manager
        )

        # Test restoration (should not raise exception)
        await restoration_service.restore_user_packages()

        # Verify the method was called
        mock_package_manager.ensure_user_packages_installed.assert_called_once()

        db_session.close()
