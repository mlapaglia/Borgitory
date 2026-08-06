"""Tests for PlatformService and macOS / Darwin support."""

from unittest.mock import MagicMock, patch

import pytest

from borgitory.services.command_execution.command_executor_factory import (
    create_command_executor,
)
from borgitory.services.command_execution.linux_command_executor import (
    LinuxCommandExecutor,
)
from borgitory.services.files.file_service_factory import create_file_service
from borgitory.services.files.linux_file_service import LinuxFileService
from borgitory.services.path.platform_service import PlatformService


class TestPlatformServiceMacOS:
    def test_is_macos_when_darwin(self) -> None:
        service = PlatformService()
        with patch.object(service, "is_docker", return_value=False):
            with patch(
                "borgitory.services.path.platform_service.platform.system",
                return_value="Darwin",
            ):
                assert service.get_platform_name() == "darwin"
                assert service.is_macos() is True
                assert service.is_linux() is False
                assert service.is_windows() is False

    def test_get_base_data_dir_macos(self) -> None:
        service = PlatformService()
        with patch.object(service, "is_docker", return_value=False):
            with patch.object(service, "is_windows", return_value=False):
                with patch.object(service, "is_linux", return_value=False):
                    with patch.object(service, "is_macos", return_value=True):
                        with patch(
                            "borgitory.services.path.platform_service.os.path.expanduser",
                            return_value="/Users/test",
                        ):
                            with patch.dict("os.environ", {}, clear=True):
                                assert service.get_base_data_dir() == (
                                    "/Users/test/Library/Application Support/Borgitory"
                                )


class TestFactoriesMacOS:
    def test_create_file_service_for_macos(self) -> None:
        platform_service = MagicMock()
        platform_service.is_windows.return_value = False
        platform_service.is_linux.return_value = False
        platform_service.is_macos.return_value = True
        platform_service.is_docker.return_value = False
        platform_service.get_platform_name.return_value = "darwin"

        service = create_file_service(MagicMock(), platform_service)

        assert isinstance(service, LinuxFileService)

    def test_create_command_executor_for_macos(self) -> None:
        platform_service = MagicMock()
        platform_service.is_windows.return_value = False
        platform_service.is_linux.return_value = False
        platform_service.is_macos.return_value = True
        platform_service.is_docker.return_value = False
        platform_service.get_platform_name.return_value = "darwin"

        executor = create_command_executor(platform_service)

        assert isinstance(executor, LinuxCommandExecutor)

    def test_create_file_service_still_rejects_unknown(self) -> None:
        platform_service = MagicMock()
        platform_service.is_windows.return_value = False
        platform_service.is_linux.return_value = False
        platform_service.is_macos.return_value = False
        platform_service.is_docker.return_value = False
        platform_service.get_platform_name.return_value = "freebsd"

        with pytest.raises(RuntimeError, match="Unknown environment freebsd"):
            create_file_service(MagicMock(), platform_service)
