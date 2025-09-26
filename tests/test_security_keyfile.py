"""
Unit tests for keyfile-related security functions in borgitory.utils.security.

These tests focus on testing the keyfile creation, cleanup, and command building
functions that were added for keyfile encryption support.
"""

import os
import tempfile
import pytest
from typing import Optional, Any
from unittest.mock import patch

from borgitory.utils.security import (
    _create_temp_keyfile,
    build_secure_borg_command_with_keyfile,
    cleanup_temp_keyfile,
    secure_borg_command,
    sanitize_path,
)


class TestCreateTempKeyfile:
    """Test _create_temp_keyfile function"""

    def test_create_temp_keyfile_success(self) -> None:
        """Test successful temporary keyfile creation"""
        keyfile_content = "test keyfile content\nwith multiple lines"

        temp_path = _create_temp_keyfile(keyfile_content)

        try:
            # Verify file was created
            assert os.path.exists(temp_path)
            assert temp_path.endswith(".key")
            assert "borg_temp_" in temp_path

            # Verify content was written correctly
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == keyfile_content

            # Verify file permissions (Unix only)
            if os.name != "nt":  # Skip on Windows
                stat = os.stat(temp_path)
                assert oct(stat.st_mode)[-3:] == "600"  # Owner read/write only

        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_create_temp_keyfile_empty_content(self) -> None:
        """Test creating temporary keyfile with empty content"""
        keyfile_content = ""

        temp_path = _create_temp_keyfile(keyfile_content)

        try:
            assert os.path.exists(temp_path)
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == ""
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @patch("tempfile.mkstemp")
    @patch("os.fdopen")
    def test_create_temp_keyfile_write_error(
        self, mock_fdopen: Any, mock_mkstemp: Any
    ) -> None:
        """Test error handling when writing keyfile fails"""
        # Mock mkstemp to return a fake file descriptor and path
        mock_fd = 123
        mock_path = "/tmp/test_keyfile"
        mock_mkstemp.return_value = (mock_fd, mock_path)

        # Mock fdopen to raise an exception
        mock_fdopen.side_effect = OSError("Write failed")

        # Mock os.unlink to track cleanup attempts
        with patch("os.unlink") as mock_unlink:
            with pytest.raises(OSError, match="Write failed"):
                _create_temp_keyfile("test content")

            # Verify cleanup was attempted
            mock_unlink.assert_called_once_with(mock_path)

    def test_create_temp_keyfile_unicode_content(self) -> None:
        """Test creating keyfile with unicode content"""
        keyfile_content = "test keyfile with unicode: ñáéíóú 🔐"

        temp_path = _create_temp_keyfile(keyfile_content)

        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == keyfile_content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestBuildSecureBorgCommandWithKeyfile:
    """Test build_secure_borg_command_with_keyfile function"""

    def test_build_command_without_keyfile(self) -> None:
        """Test building command without keyfile content"""
        command, env, temp_keyfile_path = build_secure_borg_command_with_keyfile(
            base_command="borg list",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=None,
            additional_args=["--json"],
        )

        # Should behave like regular build_secure_borg_command
        # Use sanitize_path to get the expected platform-specific path
        expected_path = sanitize_path("/test/repo")
        assert command == ["borg", "list", "--json", expected_path]
        assert env["BORG_PASSPHRASE"] == "test_pass"
        assert "BORG_KEY_FILE" not in env
        assert temp_keyfile_path is None

    def test_build_command_with_keyfile(self) -> None:
        """Test building command with keyfile content"""
        keyfile_content = "test keyfile content"

        command, env, temp_keyfile_path = build_secure_borg_command_with_keyfile(
            base_command="borg list",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=keyfile_content,
            additional_args=["--json"],
        )

        try:
            # Verify command structure
            expected_path = sanitize_path("/test/repo")
            assert command == ["borg", "list", "--json", expected_path]
            assert env["BORG_PASSPHRASE"] == "test_pass"
            assert "BORG_KEY_FILE" in env
            assert temp_keyfile_path is not None
            assert env["BORG_KEY_FILE"] == temp_keyfile_path

            # Verify keyfile was created correctly
            assert os.path.exists(temp_keyfile_path)
            with open(temp_keyfile_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == keyfile_content

        finally:
            # Clean up
            if temp_keyfile_path and os.path.exists(temp_keyfile_path):
                os.unlink(temp_keyfile_path)

    def test_build_command_with_keyfile_and_env_overrides(self) -> None:
        """Test building command with keyfile and existing environment overrides"""
        keyfile_content = "test keyfile content"
        env_overrides = {
            "BORG_RELOCATED_REPO_ACCESS_IS_OK": "no",
            "CUSTOM_VAR": "value",
        }

        command, env, temp_keyfile_path = build_secure_borg_command_with_keyfile(
            base_command="borg info",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=keyfile_content,
            environment_overrides=env_overrides,
        )

        try:
            # Verify environment variables
            assert env["BORG_PASSPHRASE"] == "test_pass"
            assert env["BORG_KEY_FILE"] == temp_keyfile_path
            assert (
                env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] == "no"
            )  # Override should work
            assert env["CUSTOM_VAR"] == "value"

        finally:
            if temp_keyfile_path and os.path.exists(temp_keyfile_path):
                os.unlink(temp_keyfile_path)

    def test_build_command_empty_repository_path(self) -> None:
        """Test building command with empty repository path (path in additional_args)"""
        keyfile_content = "test keyfile content"

        command, env, temp_keyfile_path = build_secure_borg_command_with_keyfile(
            base_command="borg create",
            repository_path="",  # Empty - path will be in additional_args
            passphrase="test_pass",
            keyfile_content=keyfile_content,
            additional_args=["--stats", "/test/repo::archive", "/source"],
        )

        try:
            # Repository path should not be appended when empty
            assert command == [
                "borg",
                "create",
                "--stats",
                "/test/repo::archive",
                "/source",
            ]
            assert env["BORG_KEY_FILE"] == temp_keyfile_path

        finally:
            if temp_keyfile_path and os.path.exists(temp_keyfile_path):
                os.unlink(temp_keyfile_path)


class TestCleanupTempKeyfile:
    """Test cleanup_temp_keyfile function"""

    def test_cleanup_existing_file(self) -> None:
        """Test cleaning up an existing temporary keyfile"""
        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".key")
        os.close(temp_fd)

        # Verify file exists
        assert os.path.exists(temp_path)

        # Clean it up
        cleanup_temp_keyfile(temp_path)

        # Verify file was deleted
        assert not os.path.exists(temp_path)

    def test_cleanup_nonexistent_file(self) -> None:
        """Test cleaning up a nonexistent file (should not raise error)"""
        nonexistent_path = "/tmp/nonexistent_keyfile_12345.key"

        # Should not raise an exception
        cleanup_temp_keyfile(nonexistent_path)

    def test_cleanup_none_path(self) -> None:
        """Test cleaning up with None path (should do nothing)"""
        # Should not raise an exception
        cleanup_temp_keyfile(None)

    @patch("os.unlink")
    def test_cleanup_permission_error(self, mock_unlink: Any) -> None:
        """Test cleanup when permission error occurs"""
        mock_unlink.side_effect = PermissionError("Permission denied")

        # Should not raise an exception, just log a warning
        cleanup_temp_keyfile("/test/path")

        mock_unlink.assert_called_once_with("/test/path")


class TestSecureBorgCommandContextManager:
    """Test secure_borg_command context manager"""

    @pytest.mark.asyncio
    async def test_context_manager_without_keyfile(self) -> None:
        """Test context manager without keyfile content"""
        async with secure_borg_command(
            base_command="borg list",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=None,
            additional_args=["--json"],
        ) as (command, env, temp_keyfile_path):
            expected_path = sanitize_path("/test/repo")
            assert command == ["borg", "list", "--json", expected_path]
            assert env["BORG_PASSPHRASE"] == "test_pass"
            assert "BORG_KEY_FILE" not in env
            assert temp_keyfile_path is None

    @pytest.mark.asyncio
    async def test_context_manager_with_keyfile_auto_cleanup(self) -> None:
        """Test context manager with keyfile and automatic cleanup"""
        keyfile_content = "test keyfile content"
        temp_keyfile_path_for_verification: Optional[str] = None

        async with secure_borg_command(
            base_command="borg list",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=keyfile_content,
            cleanup_keyfile=True,  # Default behavior
        ) as (command, env, temp_keyfile_path):
            temp_keyfile_path_for_verification = temp_keyfile_path

            # Inside context - file should exist
            assert temp_keyfile_path is not None
            assert os.path.exists(temp_keyfile_path)
            assert env["BORG_KEY_FILE"] == temp_keyfile_path

            # Verify content
            with open(temp_keyfile_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == keyfile_content

        # After context - file should be cleaned up
        assert temp_keyfile_path_for_verification is not None
        assert not os.path.exists(temp_keyfile_path_for_verification)

    @pytest.mark.asyncio
    async def test_context_manager_with_keyfile_no_cleanup(self) -> None:
        """Test context manager with keyfile but no automatic cleanup"""
        keyfile_content = "test keyfile content"
        temp_keyfile_path_for_verification: Optional[str] = None

        async with secure_borg_command(
            base_command="borg list",
            repository_path="/test/repo",
            passphrase="test_pass",
            keyfile_content=keyfile_content,
            cleanup_keyfile=False,
        ) as (command, env, temp_keyfile_path):
            temp_keyfile_path_for_verification = temp_keyfile_path

            # Inside context - file should exist
            assert temp_keyfile_path is not None
            assert os.path.exists(temp_keyfile_path)
            assert env["BORG_KEY_FILE"] == temp_keyfile_path

        try:
            # After context - file should still exist (no automatic cleanup)
            assert temp_keyfile_path_for_verification is not None
            assert os.path.exists(temp_keyfile_path_for_verification)

        finally:
            # Manual cleanup for test
            cleanup_temp_keyfile(temp_keyfile_path_for_verification)

    @pytest.mark.asyncio
    async def test_context_manager_exception_handling(self) -> None:
        """Test context manager cleanup when exception occurs"""
        keyfile_content = "test keyfile content"
        temp_keyfile_path_for_verification: Optional[str] = None

        try:
            async with secure_borg_command(
                base_command="borg list",
                repository_path="/test/repo",
                passphrase="test_pass",
                keyfile_content=keyfile_content,
                cleanup_keyfile=True,
            ) as (command, env, temp_keyfile_path):
                temp_keyfile_path_for_verification = temp_keyfile_path
                assert os.path.exists(temp_keyfile_path)

                # Raise an exception to test cleanup
                raise RuntimeError("Test exception")

        except RuntimeError:
            # Exception should be re-raised, but cleanup should still happen
            assert temp_keyfile_path_for_verification is not None
            assert not os.path.exists(temp_keyfile_path_for_verification)

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_failure(self) -> None:
        """Test context manager when cleanup fails"""
        keyfile_content = "test keyfile content"

        with patch("os.unlink") as mock_unlink:
            mock_unlink.side_effect = PermissionError("Permission denied")

            # Should not raise an exception even if cleanup fails
            async with secure_borg_command(
                base_command="borg list",
                repository_path="/test/repo",
                passphrase="test_pass",
                keyfile_content=keyfile_content,
                cleanup_keyfile=True,
            ) as (command, env, temp_keyfile_path):
                assert temp_keyfile_path is not None
                # Don't need to do anything - just testing cleanup failure

            # Verify cleanup was attempted
            mock_unlink.assert_called_once()


class TestSecurityFunctionsIntegration:
    """Integration tests for security functions working together"""

    @pytest.mark.asyncio
    async def test_full_keyfile_workflow(self) -> None:
        """Test complete keyfile workflow from creation to cleanup"""
        keyfile_content = (
            "-----BEGIN BORG KEY-----\ntest keyfile content\n-----END BORG KEY-----"
        )

        # Test the full workflow
        async with secure_borg_command(
            base_command="borg info",
            repository_path="/test/repo",
            passphrase="secure_passphrase",
            keyfile_content=keyfile_content,
            additional_args=["--json"],
            environment_overrides={"BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes"},
        ) as (command, env, temp_keyfile_path):
            # Verify command structure
            expected_path = sanitize_path("/test/repo")
            assert command == ["borg", "info", "--json", expected_path]

            # Verify environment
            assert env["BORG_PASSPHRASE"] == "secure_passphrase"
            assert env["BORG_KEY_FILE"] == temp_keyfile_path
            assert env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] == "yes"

            # Verify keyfile content
            assert temp_keyfile_path is not None
            assert os.path.exists(temp_keyfile_path)
            with open(temp_keyfile_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == keyfile_content

            # Verify file permissions (Unix only)
            if os.name != "nt":
                stat = os.stat(temp_keyfile_path)
                assert oct(stat.st_mode)[-3:] == "600"

        # After context - verify cleanup
        assert temp_keyfile_path is not None
        assert not os.path.exists(temp_keyfile_path)

    def test_manual_keyfile_lifecycle(self) -> None:
        """Test manual keyfile creation and cleanup"""
        keyfile_content = "manual keyfile test content"

        # Create keyfile manually
        temp_path = _create_temp_keyfile(keyfile_content)

        try:
            # Use it in command building
            command, env, returned_path = build_secure_borg_command_with_keyfile(
                base_command="borg list",
                repository_path="/test/repo",
                passphrase="test_pass",
                keyfile_content=keyfile_content,
            )

            # Verify both keyfiles exist (one from _create_temp_keyfile, one from build_secure_borg_command_with_keyfile)
            assert os.path.exists(temp_path)
            assert returned_path is not None
            assert os.path.exists(returned_path)
            assert temp_path != returned_path  # Should be different files

            # Verify environment
            assert env["BORG_KEY_FILE"] == returned_path

            # Clean up the returned path
            cleanup_temp_keyfile(returned_path)
            assert not os.path.exists(returned_path)

        finally:
            # Clean up our manual keyfile
            cleanup_temp_keyfile(temp_path)
