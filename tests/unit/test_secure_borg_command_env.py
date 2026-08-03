"""Tests for secure Borg command environment handling."""

import os

from borgitory.utils.security import build_secure_borg_command


class TestBuildSecureBorgCommandEnvironment:
    def test_preserves_path_from_process_environment(self) -> None:
        command, environment = build_secure_borg_command(
            base_command="borg init",
            repository_path="/tmp/test-repo",
            passphrase="secret",
            additional_args=["--encryption=repokey"],
        )

        assert "PATH" in environment
        assert environment["PATH"] == os.environ.get("PATH", "")
        assert environment["BORG_PASSPHRASE"] == "secret"
        assert environment["BORG_RELOCATED_REPO_ACCESS_IS_OK"] == "yes"
        assert command[0] == "borg"
        assert "--encryption=repokey" in command

    def test_environment_overrides_applied(self) -> None:
        _, environment = build_secure_borg_command(
            base_command="borg info",
            repository_path="/tmp/test-repo",
            environment_overrides={"BORG_CACHE_DIR": "/custom/cache"},
        )

        assert environment["BORG_CACHE_DIR"] == "/custom/cache"
