"""
Tests for WSLCommandExecutor.

Tests the WSL command executor implementation for Windows environments.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch

from borgitory.services.command_execution.wsl_command_executor import WSLCommandExecutor


class TestWSLCommandExecutor:
    """Test cases for WSLCommandExecutor."""

    @pytest.fixture
    def executor(self) -> WSLCommandExecutor:
        """Create a WSL command executor for testing."""
        return WSLCommandExecutor(timeout=10.0)

    @pytest.fixture
    def executor_with_distribution(self) -> WSLCommandExecutor:
        """Create a WSL command executor with specific distribution."""
        return WSLCommandExecutor(distribution="Ubuntu-20.04", timeout=15.0)

    def test_init_default(self) -> None:
        """Test WSLCommandExecutor initialization with defaults."""
        executor = WSLCommandExecutor()
        assert executor.distribution is None
        assert executor.default_timeout == 300.0

    def test_init_with_params(self) -> None:
        """Test WSLCommandExecutor initialization with parameters."""
        executor = WSLCommandExecutor(distribution="Ubuntu-20.04", timeout=60.0)
        assert executor.distribution == "Ubuntu-20.04"
        assert executor.default_timeout == 60.0

    def test_get_platform_name(self, executor: WSLCommandExecutor) -> None:
        """Test get_platform_name returns correct value."""
        assert executor.get_platform_name() == "wsl"

    def test_build_wsl_command_basic(self, executor: WSLCommandExecutor) -> None:
        """Test building basic WSL command."""
        command = ["ls", "-la"]
        result = executor._build_wsl_command(command)

        expected = ["wsl", "/bin/bash", "-l", "-c", "ls -la"]
        assert result == expected

    def test_build_wsl_command_with_distribution(
        self, executor_with_distribution: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with specific distribution."""
        command = ["pwd"]
        result = executor_with_distribution._build_wsl_command(command)

        expected = ["wsl", "-d", "Ubuntu-20.04", "/bin/bash", "-l", "-c", "pwd"]
        assert result == expected

    def test_build_wsl_command_with_cwd(self, executor: WSLCommandExecutor) -> None:
        """Test building WSL command with working directory."""
        command = ["ls"]
        cwd = "/home/user/documents"
        result = executor._build_wsl_command(command, cwd=cwd)

        expected = ["wsl", "/bin/bash", "-l", "-c", "cd '/home/user/documents' && ls"]
        assert result == expected

    def test_build_wsl_command_with_env(self, executor: WSLCommandExecutor) -> None:
        """Test building WSL command with environment variables."""
        command = ["borg", "list"]
        env = {
            "BORG_REPO": "/path/to/repo",
            "BORG_PASSPHRASE": "secret123",
            "BORGITORY_DEBUG": "1",
            "UNRELATED_VAR": "should_be_filtered",
        }
        result = executor._build_wsl_command(command, env=env)

        # Should only include BORG_ and BORGITORY_ prefixed variables
        shell_command = result[-1]
        assert "export BORG_REPO='/path/to/repo'" in shell_command
        assert "export BORG_PASSPHRASE='secret123'" in shell_command
        assert "export BORGITORY_DEBUG='1'" in shell_command
        assert "UNRELATED_VAR" not in shell_command

    def test_build_wsl_command_with_spaces_in_args(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with arguments containing spaces."""
        command = ["echo", "hello world", "test file.txt"]
        result = executor._build_wsl_command(command)

        shell_command = result[-1]
        assert 'echo "hello world" "test file.txt"' in shell_command

    def test_build_wsl_command_with_quotes_in_args(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with arguments containing quotes."""
        command = ["echo", 'say "hello"']
        result = executor._build_wsl_command(command)

        shell_command = result[-1]
        assert 'echo "say \\"hello\\""' in shell_command

    def test_build_wsl_command_with_env_quotes(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with environment variables containing quotes."""
        command = ["test"]
        env = {"BORG_PASSPHRASE": "pass'word\"test"}
        result = executor._build_wsl_command(command, env=env)

        shell_command = result[-1]
        # Single quotes in env values should be escaped properly
        assert "export BORG_PASSPHRASE='pass'\"'\"'word\"test'" in shell_command

    def test_build_wsl_command_direct_wsl_exe(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test that wsl.exe commands are passed through directly."""
        command = ["wsl.exe", "--list", "--verbose"]
        result = executor._build_wsl_command(command)

        assert result == command

    @pytest.mark.asyncio
    async def test_execute_command_success(self, executor: WSLCommandExecutor) -> None:
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

            # Verify WSL command was built correctly
            mock_create.assert_called_once()
            args = mock_create.call_args[1]
            assert args["stdout"] == asyncio.subprocess.PIPE
            assert args["stderr"] == asyncio.subprocess.PIPE

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, executor: WSLCommandExecutor) -> None:
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
    async def test_execute_command_with_input(
        self, executor: WSLCommandExecutor
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
            mock_process.communicate.assert_called_once_with(input=b"test input")

            # Verify stdin was set up
            args = mock_create.call_args[1]
            assert args["stdin"] == asyncio.subprocess.PIPE

    @pytest.mark.asyncio
    async def test_execute_command_timeout(self, executor: WSLCommandExecutor) -> None:
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
    async def test_execute_command_exception(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test command execution with exception."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=OSError("Permission denied")
        ):
            result = await executor.execute_command(["test"])

            assert result.success is False
            assert result.return_code == -1
            assert result.error is not None
            assert "WSL command execution failed: Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_command_with_all_params(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test command execution with all parameters."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        env = {"BORG_REPO": "/repo"}
        cwd = "/home/user"

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute_command(
                ["borg", "list"], env=env, cwd=cwd, timeout=30.0, input_data="input"
            )

            assert result.success is True
            assert result.command == ["borg", "list"]

    @pytest.mark.asyncio
    async def test_execute_command_no_such_file_warning_suppressed(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test that 'No such file or directory' warnings are suppressed."""
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"No such file or directory")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch(
                "borgitory.services.command_execution.wsl_command_executor.logger"
            ) as mock_logger:
                result = await executor.execute_command(["test", "-f", "nonexistent"])

                assert result.success is False
                # Should not log warning for "No such file or directory"
                mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_subprocess(self, executor: WSLCommandExecutor) -> None:
        """Test subprocess creation for streaming."""
        mock_process = Mock()

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            process = await executor.create_subprocess(
                ["borg", "create"],
                env={"BORG_REPO": "/repo"},
                cwd="/home/user",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            assert process == mock_process
            mock_create.assert_called_once()

            # Check that WSL command was built and passed to create_subprocess_exec
            call_args = mock_create.call_args
            wsl_command = call_args[0]
            assert wsl_command[0] == "wsl"
            assert "bash" in wsl_command

            kwargs = call_args[1]
            assert kwargs["stdout"] == asyncio.subprocess.PIPE
            # For FIFO streaming, stderr is redirected to stdout
            assert kwargs["stderr"] == asyncio.subprocess.STDOUT

    @pytest.mark.asyncio
    async def test_create_subprocess_default_pipes(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test subprocess creation with default pipe settings."""
        mock_process = Mock()

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_create:
            await executor.create_subprocess(["echo", "test"])

            kwargs = mock_create.call_args[1]
            # When no pipes are specified, they should be None (default behavior)
            assert kwargs.get("stdout") is None
            assert kwargs.get("stderr") is None

    def test_build_wsl_command_complex_scenario(
        self, executor_with_distribution: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with complex scenario."""
        command = ["borg", "create", "--stats", "::backup-{now}", "/home/user/data"]
        env = {
            "BORG_REPO": "/mnt/backup/repo",
            "BORG_PASSPHRASE": "complex'pass\"word",
            "BORGITORY_LOG_LEVEL": "DEBUG",
        }
        cwd = "/home/user"

        result = executor_with_distribution._build_wsl_command(command, env, cwd)

        expected_start = ["wsl", "-d", "Ubuntu-20.04", "/bin/bash", "-l", "-c"]
        assert result[:6] == expected_start

        shell_command = result[6]
        assert "export BORG_REPO='/mnt/backup/repo'" in shell_command
        assert "export BORG_PASSPHRASE='complex'\"'\"'pass\"word'" in shell_command
        assert "export BORGITORY_LOG_LEVEL='DEBUG'" in shell_command
        assert "cd '/home/user'" in shell_command
        assert "borg create --stats ::backup-{now} /home/user/data" in shell_command
        assert " && " in shell_command  # Commands should be chained

    @pytest.mark.asyncio
    async def test_execute_command_utf8_handling(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test proper UTF-8 handling in command output."""
        # Test with UTF-8 content
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
        self, executor: WSLCommandExecutor
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

    def test_build_wsl_command_empty_command(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with empty command list."""
        result = executor._build_wsl_command([])

        expected = ["wsl", "/bin/bash", "-l", "-c", ""]
        assert result == expected

    def test_build_wsl_command_single_command(
        self, executor: WSLCommandExecutor
    ) -> None:
        """Test building WSL command with single command."""
        result = executor._build_wsl_command(["pwd"])

        expected = ["wsl", "/bin/bash", "-l", "-c", "pwd"]
        assert result == expected
