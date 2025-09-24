"""
Tests for PackageManagerService
"""

import pytest
from unittest.mock import AsyncMock
from borgitory.services.package_manager_service import PackageManagerService
from borgitory.protocols.command_protocols import CommandResult


class MockCommandRunner:
    """Mock command runner for testing"""

    def __init__(self):
        self._run_command_mock = AsyncMock()

    async def run_command(self, command, timeout=None, **kwargs):
        return await self._run_command_mock(command, timeout=timeout, **kwargs)


@pytest.fixture
def mock_command_runner():
    return MockCommandRunner()


@pytest.fixture
def package_service(mock_command_runner):
    return PackageManagerService(command_runner=mock_command_runner)


class TestPackageManagerService:
    @pytest.mark.asyncio
    async def test_search_packages_empty_cache(
        self, package_service, mock_command_runner
    ):
        """Test searching packages with empty cache"""
        # Mock apt-cache search response
        mock_command_runner._run_command_mock.return_value = CommandResult(
            success=True,
            return_code=0,
            stdout="curl - command line tool for transferring data\njq - lightweight JSON processor\n",
            stderr="",
            duration=0.5,
        )

        results = await package_service.search_packages("curl", limit=10)

        assert len(results) >= 1
        assert any(pkg.name == "curl" for pkg in results)
        mock_command_runner._run_command_mock.assert_called_once_with(
            ["apt-cache", "search", "."], timeout=30
        )

    @pytest.mark.asyncio
    async def test_get_package_info_success(self, package_service, mock_command_runner):
        """Test getting package info for existing package"""
        # Mock apt-cache show response
        apt_show_output = """Package: curl
Version: 7.81.0-1ubuntu1.15
Description: command line tool for transferring data
Section: web
"""
        mock_command_runner._run_command_mock.side_effect = [
            CommandResult(
                success=True,
                return_code=0,
                stdout=apt_show_output,
                stderr="",
                duration=0.1,
            ),
            CommandResult(  # dpkg check for installed status
                success=False, return_code=1, stdout="", stderr="", duration=0.1
            ),
        ]

        result = await package_service.get_package_info("curl")

        assert result is not None
        assert result.name == "curl"
        assert result.version == "7.81.0-1ubuntu1.15"
        assert "command line tool" in result.description
        assert result.section == "web"
        assert result.installed is False

    @pytest.mark.asyncio
    async def test_get_package_info_not_found(
        self, package_service, mock_command_runner
    ):
        """Test getting package info for non-existent package"""
        mock_command_runner._run_command_mock.return_value = CommandResult(
            success=False,
            return_code=100,
            stdout="",
            stderr="E: No packages found",
            duration=0.1,
        )

        result = await package_service.get_package_info("nonexistent-package")

        assert result is None

    @pytest.mark.asyncio
    async def test_install_packages_success(self, package_service, mock_command_runner):
        """Test successful package installation"""
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
                success=False,  # No DB session, so tracking will be skipped
                return_code=1,
                stdout="",
                stderr="",
                duration=0.1,
            ),
        ]

        success, message = await package_service.install_packages(["curl"])

        assert success is True
        assert "Successfully installed: curl" in message
        # Now expects 4 calls: update, install, apt-cache show, dpkg -l
        assert mock_command_runner._run_command_mock.call_count == 4

    @pytest.mark.asyncio
    async def test_install_packages_failure(self, package_service, mock_command_runner):
        """Test failed package installation"""
        mock_command_runner._run_command_mock.side_effect = [
            CommandResult(  # apt-get update
                success=True,
                return_code=0,
                stdout="Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease\n",
                stderr="",
                duration=2.0,
            ),
            CommandResult(  # apt-get install fails
                success=False,
                return_code=100,
                stdout="",
                stderr="E: Unable to locate package nonexistent-package",
                duration=1.0,
            ),
        ]

        success, message = await package_service.install_packages(
            ["nonexistent-package"]
        )

        assert success is False
        assert "Installation failed" in message
        assert "Unable to locate package" in message

    @pytest.mark.asyncio
    async def test_remove_packages_success(self, package_service, mock_command_runner):
        """Test successful package removal"""
        mock_command_runner._run_command_mock.return_value = CommandResult(
            success=True,
            return_code=0,
            stdout="Reading package lists...\nThe following packages will be REMOVED:\n  curl\n",
            stderr="",
            duration=3.0,
        )

        success, message = await package_service.remove_packages(["curl"])

        assert success is True
        assert "Successfully removed: curl" in message

    @pytest.mark.asyncio
    async def test_list_installed_packages(self, package_service, mock_command_runner):
        """Test listing installed packages"""
        dpkg_output = "curl\t7.81.0-1ubuntu1.15\tinstall ok installed\njq\t1.6-2.1ubuntu3\tinstall ok installed\n"
        mock_command_runner._run_command_mock.return_value = CommandResult(
            success=True, return_code=0, stdout=dpkg_output, stderr="", duration=0.5
        )

        packages = await package_service.list_installed_packages()

        assert len(packages) == 2
        assert packages[0].name == "curl"
        assert packages[0].version == "7.81.0-1ubuntu1.15"
        assert packages[0].installed is True
        assert packages[1].name == "jq"
        assert packages[1].version == "1.6-2.1ubuntu3"

    @pytest.mark.asyncio
    async def test_validate_package_names_valid(self, package_service):
        """Test package name validation with valid names"""
        valid_packages = ["curl", "jq", "postgresql-client", "python3-pip"]
        result = package_service._validate_package_names(valid_packages)
        assert result == valid_packages

    @pytest.mark.asyncio
    async def test_validate_package_names_invalid(self, package_service):
        """Test package name validation with invalid names"""
        with pytest.raises(ValueError, match="Invalid package name"):
            package_service._validate_package_names(["curl; rm -rf /"])

        with pytest.raises(ValueError, match="Invalid package name"):
            package_service._validate_package_names(["../../../etc/passwd"])

        with pytest.raises(ValueError, match="Package name too long"):
            package_service._validate_package_names(["a" * 101])
