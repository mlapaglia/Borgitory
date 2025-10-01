"""
Tests for LinuxCommandExecutor.

Tests the Linux command executor implementation for Linux and Docker environments.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch

from borgitory.services.command_execution.linux_command_executor import (
    LinuxCommandExecutor,
)


class TestLinuxCommandExecutor:
    """Test cases for LinuxCommandExecutor."""

    @pytest.fixture
    def executor(self) -> LinuxCommandExecutor:
        """Create a Linux command executor for testing."""
        return LinuxCommandExecutor(default_timeout=10.0)

    def test_init_default(self) -> None:
        """Test LinuxCommandExecutor initialization with defaults."""
        executor = LinuxCommandExecutor()
        assert executor.default_timeout == 300.0

    def test_init_with_timeout(self) -> None:
        """Test LinuxCommandExecutor initialization with custom timeout."""
        executor = LinuxCommandExecutor(default_timeout=60.0)
        assert executor.default_timeout == 60.0

    def test_get_platform_name(self, executor: LinuxCommandExecutor) -> None:
        """Test get_platform_name returns correct value."""
        assert executor.get_platform_name() == "linux"

    @pytest.mark.asyncio
    async def test_execute_command_success(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test successful command execution."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(["echo", "test"])

            assert result.success is True
            assert result.return_code == 0
            assert result.stdout == "output"
            assert result.stderr == ""
            assert result.error is None
            assert result.command == ["echo", "test"]
            assert result.execution_time > 0

            # Verify subprocess was created correctly
            mock_create.assert_called_once_with(
                "echo",
                "test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=None,
                env=None,
                cwd=None,
            )

    @pytest.mark.asyncio
    async def test_execute_command_failure(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test failed command execution."""
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(["false"])

            assert result.success is False
            assert result.return_code == 1
            assert result.stdout == ""
            assert result.stderr == "error message"
            assert result.error == "error message"

    @pytest.mark.asyncio
    async def test_execute_command_with_env(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with environment variables."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        env = {"BORG_REPO": "/path/to/repo", "BORG_PASSPHRASE": "secret"}

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(["borg", "list"], env=env)

            assert result.success is True

            # Verify environment was passed
            mock_create.assert_called_once_with(
                "borg",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=None,
                env=env,
                cwd=None,
            )

    @pytest.mark.asyncio
    async def test_execute_command_with_cwd(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with working directory."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        cwd = "/home/user/documents"

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(["ls"], cwd=cwd)

            assert result.success is True

            # Verify working directory was set
            mock_create.assert_called_once_with(
                "ls",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=None,
                env=None,
                cwd=cwd,
            )

    @pytest.mark.asyncio
    async def test_execute_command_with_input(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with input data."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"processed", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(["cat"], input_data="test input")

            assert result.success is True
            mock_process.communicate.assert_called_once_with(b"test input")

            # Verify stdin was set up
            mock_create.assert_called_once_with(
                "cat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=None,
                cwd=None,
            )

    @pytest.mark.asyncio
    async def test_execute_command_timeout(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution timeout."""
        mock_process = Mock()
        mock_process.kill = Mock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await executor.execute_command(["sleep", "100"], timeout=1.0)

                assert result.success is False
                assert result.return_code == -1
                assert result.error is not None
                assert "timed out after 1.0 seconds" in result.error
                mock_process.kill.assert_called_once()
                mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_custom_timeout(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with custom timeout."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for") as mock_wait_for:
                mock_wait_for.return_value = (b"success", b"")

                await executor.execute_command(["test"], timeout=5.0)

                # Verify custom timeout was used
                mock_wait_for.assert_called_once()
                assert mock_wait_for.call_args[1]["timeout"] == 5.0

    @pytest.mark.asyncio
    async def test_execute_command_default_timeout(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution uses default timeout when none specified."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for") as mock_wait_for:
                mock_wait_for.return_value = (b"success", b"")

                await executor.execute_command(["test"])

                # Verify default timeout was used
                mock_wait_for.assert_called_once()
                assert mock_wait_for.call_args[1]["timeout"] == executor.default_timeout

    @pytest.mark.asyncio
    async def test_execute_command_exception(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with exception."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("Permission denied")
        ):
            result = await executor.execute_command(["test"])

            assert result.success is False
            assert result.error is not None
            assert result.return_code == -1
            assert "Linux command execution failed: Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_command_with_all_params(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with all parameters."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        env = {"BORG_REPO": "/repo", "PATH": "/usr/bin"}
        cwd = "/home/user"

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(
                ["borg", "list", "--verbose"],
                env=env,
                cwd=cwd,
                timeout=30.0,
                input_data="input data",
            )

            assert result.success is True
            assert result.command == ["borg", "list", "--verbose"]

            # Verify all parameters were passed correctly
            mock_create.assert_called_once_with(
                "borg",
                "list",
                "--verbose",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )

            mock_process.communicate.assert_called_once_with(b"input data")

    @pytest.mark.asyncio
    async def test_execute_command_none_returncode(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution when process returncode is None."""
        mock_process = Mock()
        mock_process.returncode = None
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(["test"])

            assert result.return_code == 0  # Should default to 0 when None

    @pytest.mark.asyncio
    async def test_execute_command_stderr_without_failure(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with stderr but successful return code."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"output", b"warning message")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(["test"])

            assert result.success is True
            assert result.stderr == "warning message"
            assert result.error is None  # No error since command succeeded

    @pytest.mark.asyncio
    async def test_create_subprocess(self, executor: LinuxCommandExecutor) -> None:
        """Test subprocess creation for streaming."""
        mock_process = Mock()
        mock_process.pid = 12345

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            process = await executor.create_subprocess(
                ["borg", "create"],
                env={"BORG_REPO": "/repo"},
                cwd="/home/user",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )

            assert process == mock_process

            mock_create.assert_called_once_with(
                "borg",
                "create",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env={"BORG_REPO": "/repo"},
                cwd="/home/user",
            )

    @pytest.mark.asyncio
    async def test_create_subprocess_default_pipes(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test subprocess creation with default pipe settings."""
        mock_process = Mock()
        mock_process.pid = 12345

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            await executor.create_subprocess(["echo", "test"])

            mock_create.assert_called_once_with(
                "echo",
                "test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=None,
                env=None,
                cwd=None,
            )

    @pytest.mark.asyncio
    async def test_create_subprocess_exception(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test subprocess creation with exception."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("Command not found")
        ):
            with pytest.raises(OSError, match="Command not found"):
                await executor.create_subprocess(["nonexistent"])

    @pytest.mark.asyncio
    async def test_execute_command_utf8_handling(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test proper UTF-8 handling in command output."""
        utf8_content = "Hello 世界 🌍"
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(utf8_content.encode("utf-8"), "".encode("utf-8"))
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(["echo", "test"])

            assert result.success is True
            assert result.stdout == utf8_content

    @pytest.mark.asyncio
    async def test_execute_command_invalid_utf8_handling(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test handling of invalid UTF-8 sequences."""
        mock_process = Mock()
        mock_process.returncode = 0
        # Invalid UTF-8 sequence
        invalid_utf8 = b"\xff\xfe\x00\x00invalid"
        mock_process.communicate = AsyncMock(return_value=(invalid_utf8, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(["test"])

            assert result.success is True
            # Should handle invalid UTF-8 gracefully with replacement characters
            assert isinstance(result.stdout, str)

    @pytest.mark.asyncio
    async def test_execute_command_empty_command(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test command execution with empty command list."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command([])

            assert result.success is True
            # Should still call create_subprocess_exec even with empty command
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_complex_command(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test execution of complex command with many arguments."""
        complex_command = [
            "borg",
            "create",
            "--verbose",
            "--stats",
            "--compression",
            "lz4",
            "::backup-{now:%Y-%m-%d_%H:%M:%S}",
            "/home/user/documents",
            "/home/user/pictures",
        ]

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Archive created", b""))

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            result = await executor.execute_command(complex_command)

            assert result.success is True
            assert result.command == complex_command

            # Verify all command arguments were passed
            call_args = mock_create.call_args[0]
            assert call_args == tuple(complex_command)

    @pytest.mark.asyncio
    async def test_execute_command_logging_success(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test that successful commands are logged appropriately."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "borgitory.services.command_execution.linux_command_executor.logger"
            ) as mock_logger:
                await executor.execute_command(["echo", "test"])

                # Should log debug message for successful command
                mock_logger.debug.assert_called()
                debug_calls = [
                    call.args[0] for call in mock_logger.debug.call_args_list
                ]
                assert any("completed successfully" in msg for msg in debug_calls)

    @pytest.mark.asyncio
    async def test_execute_command_logging_failure(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test that failed commands are logged appropriately."""
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"command failed"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "borgitory.services.command_execution.linux_command_executor.logger"
            ) as mock_logger:
                await executor.execute_command(["false"])

                # Should log warning for failed command
                mock_logger.warning.assert_called_once()
                warning_msg = mock_logger.warning.call_args[0][0]
                assert "failed" in warning_msg
                assert "code 1" in warning_msg

    @pytest.mark.asyncio
    async def test_create_subprocess_logging(
        self, executor: LinuxCommandExecutor
    ) -> None:
        """Test that subprocess creation is logged appropriately."""
        mock_process = Mock()
        mock_process.pid = 12345

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "borgitory.services.command_execution.linux_command_executor.logger"
            ) as mock_logger:
                await executor.create_subprocess(["test"])

                # Should log debug messages for subprocess creation
                mock_logger.debug.assert_called()
                debug_calls = [
                    call.args[0] for call in mock_logger.debug.call_args_list
                ]
                assert any("Creating Linux subprocess" in msg for msg in debug_calls)
                assert any(
                    "subprocess created successfully" in msg for msg in debug_calls
                )
