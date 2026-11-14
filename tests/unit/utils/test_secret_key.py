import os
import stat
import sys
from pathlib import Path

import pytest

from borgitory.utils.security import get_or_generate_secret_key

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file permissions"
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_generated_secret_key_is_owner_only(tmp_path: Path) -> None:
    key = get_or_generate_secret_key(str(tmp_path))

    secret_file = tmp_path / "secret_key"
    assert secret_file.read_text() == key
    assert _mode(secret_file) == 0o600


def test_existing_secret_key_is_reused_and_restricted(tmp_path: Path) -> None:
    secret_file = tmp_path / "secret_key"
    secret_file.write_text("existing-key\n")
    os.chmod(secret_file, 0o644)

    assert get_or_generate_secret_key(str(tmp_path)) == "existing-key"
    assert _mode(secret_file) == 0o600
