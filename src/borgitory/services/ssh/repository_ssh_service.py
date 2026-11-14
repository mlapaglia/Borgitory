"""
SSH support for remote (ssh://) borg repositories.

Borg talks to remote repositories by spawning ``ssh`` itself, configured via the
BORG_RSH environment variable. Each repository may carry its own private key,
stored encrypted in the database; it is materialized to a 0600 file under
DATA_DIR/ssh/keys so it can be referenced from BORG_RSH for the lifetime of any
borg process (including long-running jobs).
"""

import hashlib
import logging
import os
import re
import shlex
from typing import Optional

from borgitory.config_module import DATA_DIR
from borgitory.utils.security import is_remote_repository_path

logger = logging.getLogger(__name__)

SSH_CONNECT_TIMEOUT_SECONDS = 20


def _ssh_dir() -> str:
    return os.path.join(DATA_DIR, "ssh")


def known_hosts_path() -> str:
    return os.path.join(_ssh_dir(), "known_hosts")


def key_file_path(repository_id: int) -> str:
    return os.path.join(_ssh_dir(), "keys", f"repo_{repository_id}")


def pending_key_file_path(ssh_private_key: str) -> str:
    """Key file for a repository that has no id yet (create/import in progress)."""
    digest = hashlib.sha256(normalize_private_key(ssh_private_key).encode()).hexdigest()
    return os.path.join(_ssh_dir(), "keys", f"pending_{digest[:32]}")


def _to_executor_path(path: str) -> str:
    """Translate a Windows host path to its WSL mount so ssh inside WSL can read it."""
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    if not match:
        return path
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/" + rest.replace("\\", "/")


def normalize_private_key(ssh_private_key: str) -> str:
    """Normalize pasted key text; OpenSSH rejects CRLF endings and a missing final newline."""
    return ssh_private_key.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def write_key_file(repository_id: Optional[int], ssh_private_key: str) -> str:
    """
    Write the repository's private key to disk (0600), only if it changed.

    A repository without an id yet gets a pending key file, which the caller
    removes with delete_pending_key_file once creation or import finishes.
    """
    path = (
        key_file_path(repository_id)
        if repository_id is not None
        else pending_key_file_path(ssh_private_key)
    )
    content = normalize_private_key(ssh_private_key).encode()

    if os.path.exists(path):
        with open(path, "rb") as existing:
            if existing.read() == content:
                return path

    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
    # O_CREAT's mode is ignored when the file already existed
    os.chmod(path, 0o600)
    return path


def _remove_key_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"Failed to remove SSH key file {path}: {e}")


def delete_key_file(repository_id: int) -> None:
    """Remove a repository's materialized key file, if present."""
    _remove_key_file(key_file_path(repository_id))


def delete_pending_key_file(ssh_private_key: Optional[str]) -> None:
    """Remove the key file written for a repository that had no id yet, if present."""
    if ssh_private_key:
        _remove_key_file(pending_key_file_path(ssh_private_key))


def _ssh_config_quote(value: str) -> str:
    """Quote a value for ssh's own option parser, which splits on whitespace."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_ssh_env_overrides(
    repository_id: Optional[int],
    repository_path: Optional[str],
    ssh_private_key: Optional[str],
    remote_borg_path: Optional[str],
) -> dict[str, str]:
    """
    Build BORG_RSH / BORG_REMOTE_PATH for a remote repository.

    Returns an empty dict for local repositories. Unknown hosts are trusted on
    first connect and pinned in DATA_DIR/ssh/known_hosts, which lives on the
    persistent data volume.
    """
    if not is_remote_repository_path(repository_path):
        return {}

    os.makedirs(_ssh_dir(), mode=0o700, exist_ok=True)

    rsh = ["ssh"]
    if ssh_private_key:
        key_path = write_key_file(repository_id, ssh_private_key)
        rsh += ["-i", _to_executor_path(key_path), "-o", "IdentitiesOnly=yes"]
    rsh += [
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
        "-o",
        f"UserKnownHostsFile={_ssh_config_quote(_to_executor_path(known_hosts_path()))}",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]

    env = {"BORG_RSH": " ".join(shlex.quote(part) for part in rsh)}
    if remote_borg_path:
        env["BORG_REMOTE_PATH"] = remote_borg_path
    return env
