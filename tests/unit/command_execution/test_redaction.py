from borgitory.services.command_execution.redaction import redact_command


def test_masks_value_after_sensitive_flag() -> None:
    cmd = ["rclone", "lsd", ":s3:b", "--s3-secret-access-key", "hunter2", "-v"]
    assert redact_command(cmd) == "rclone lsd :s3:b --s3-secret-access-key *** -v"


def test_masks_equals_form() -> None:
    assert redact_command(["x", "--sftp-pass=hunter2"]) == "x --sftp-pass=***"


def test_masks_shell_exports() -> None:
    cmd = ["wsl", "bash", "-c", "export BORG_PASSPHRASE='hunter2'; borg list"]
    out = redact_command(cmd)
    assert "hunter2" not in out
    assert "export BORG_PASSPHRASE=***; borg list" in out


def test_leaves_ordinary_arguments_alone() -> None:
    cmd = ["borg", "prune", "--keep-daily", "7", "/repo"]
    assert redact_command(cmd) == "borg prune --keep-daily 7 /repo"
