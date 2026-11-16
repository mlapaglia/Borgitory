"""Credentials must reach rclone via environment variables, never argv."""

from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from borgitory.protocols.command_executor_protocol import CommandResult
from borgitory.services.cloud_providers.storage.pcloud_storage import (
    PcloudStorage,
    PcloudStorageConfig,
)
from borgitory.services.cloud_providers.storage.rclone_credentials import (
    RcloneObscureError,
    build_rclone_env,
    obscure_password,
)
from borgitory.services.cloud_providers.storage.s3_storage import (
    S3Storage,
    S3StorageConfig,
)
from borgitory.services.cloud_providers.storage.smb_storage import (
    SMBStorage,
    SMBStorageConfig,
)
from borgitory.services.cloud_providers.storage.sftp_storage import (
    SFTPStorage,
    SFTPStorageConfig,
)

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def _result(stdout: str = "", success: bool = True) -> CommandResult:
    return CommandResult(
        command=[],
        return_code=0 if success else 1,
        stdout=stdout,
        stderr="" if success else "boom",
        success=success,
        execution_time=0.0,
    )


def _executor(stdout: str = "OBSCURED") -> MagicMock:
    executor = MagicMock()
    executor.execute_command = AsyncMock(return_value=_result(stdout))
    return executor


def _all_args(executor: MagicMock) -> List[str]:
    args: List[str] = []
    for call in executor.execute_command.call_args_list:
        args.extend(call.kwargs["command"])
    return args


def test_build_rclone_env_skips_empty_values() -> None:
    env = build_rclone_env({"RCLONE_A": "x", "RCLONE_B": None, "RCLONE_C": ""})
    assert env["RCLONE_A"] == "x"
    assert "RCLONE_B" not in env and "RCLONE_C" not in env
    assert "PATH" in env


async def test_obscure_password_uses_stdin() -> None:
    executor = _executor("OBSCURED")
    assert await obscure_password(executor, "hunter2") == "OBSCURED"
    call = executor.execute_command.call_args
    assert call.kwargs["command"] == ["rclone", "obscure", "-"]
    assert "hunter2" in call.kwargs["input_data"]


async def test_obscure_password_raises_instead_of_falling_back() -> None:
    executor = MagicMock()
    executor.execute_command = AsyncMock(return_value=_result(success=False))
    with pytest.raises(RcloneObscureError):
        await obscure_password(executor, "hunter2")


async def test_s3_secret_passed_via_env() -> None:
    executor = _executor()
    storage = S3Storage(
        S3StorageConfig(
            access_key="AKIAIOSFODNN7EXAMPLE", secret_key=SECRET, bucket_name="bkt"
        ),
        executor,
        MagicMock(),
    )
    storage._test_s3_write_permissions = AsyncMock(  # type: ignore[method-assign]
        return_value={"status": "success"}
    )
    await storage.test_s3_connection("AKIAIOSFODNN7EXAMPLE", SECRET, "bkt")

    assert SECRET not in _all_args(executor)
    env = executor.execute_command.call_args.kwargs["env"]
    assert env["RCLONE_S3_SECRET_ACCESS_KEY"] == SECRET
    assert env["RCLONE_S3_ACCESS_KEY_ID"] == "AKIAIOSFODNN7EXAMPLE"


async def test_pcloud_token_passed_via_env() -> None:
    token = '{"access_token":"abc123"}'
    executor = _executor()
    storage = PcloudStorage(PcloudStorageConfig(token=token), executor, MagicMock())
    await storage.test_pcloud_connection(token)

    assert token not in _all_args(executor)
    assert (
        executor.execute_command.call_args.kwargs["env"]["RCLONE_PCLOUD_TOKEN"] == token
    )


async def test_sftp_password_passed_obscured_via_env() -> None:
    executor = _executor("OBSCURED")
    storage = SFTPStorage(
        SFTPStorageConfig(
            host="h", username="u", password="hunter2", remote_path="/backups"
        ),
        executor,
        MagicMock(),
    )
    async with storage._build_sftp_flags("h", "u", 22, "hunter2") as (flags, env):
        assert "hunter2" not in flags and "OBSCURED" not in flags
        assert env["RCLONE_SFTP_PASS"] == "OBSCURED"


async def test_smb_password_passed_obscured_via_env() -> None:
    executor = _executor("OBSCURED")
    storage = SMBStorage(
        SMBStorageConfig.model_validate(
            {"host": "h", "user": "u", "pass": "hunter2", "share_name": "s"}
        ),
        executor,
        MagicMock(),
    )
    env = await storage._build_smb_env("hunter2")
    flags = storage._build_smb_flags("h", "u")
    assert env["RCLONE_SMB_PASS"] == "OBSCURED"
    assert "hunter2" not in flags and "OBSCURED" not in flags
