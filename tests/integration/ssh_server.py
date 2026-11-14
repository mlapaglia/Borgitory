"""
A throwaway OpenSSH server for integration tests of remote (ssh://) repositories.

sshd runs as the current user on a random localhost port, with its own host key,
authorized_keys and config in a temporary directory, so it needs no root access
(when the tests do run as root, as in the CI container, it logs in as root with
a key). Remote borg is the same borg binary as the client, passed as the
repository's remote borg path, so repositories live on the local filesystem.
"""

import getpass
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SSHD_SEARCH_PATH = os.pathsep.join(
    [os.environ.get("PATH", ""), "/usr/sbin", "/usr/local/sbin", "/sbin"]
)


def find_sshd() -> Optional[str]:
    return shutil.which("sshd", path=SSHD_SEARCH_PATH)


def missing_tools() -> list[str]:
    """Names of the executables these tests need that aren't installed."""
    missing = [tool for tool in ("ssh", "ssh-keygen", "borg") if not shutil.which(tool)]
    if not find_sshd():
        missing.append("sshd")
    return missing


def generate_key(path: Path) -> str:
    """Create an ed25519 key pair at path / path.pub and return the private key."""
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(path)],
        check=True,
    )
    return path.read_text()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class SshServer:
    root: Path
    port: int
    user: str
    borg_path: str
    client_key: str
    host_key_pub: str
    process: Optional["subprocess.Popen[bytes]"] = field(default=None, repr=False)

    @property
    def log_path(self) -> Path:
        return self.root / "sshd.log"

    @property
    def authorized_keys(self) -> Path:
        return self.root / "authorized_keys"

    def url(self, repository_path: Path) -> str:
        return f"ssh://{self.user}@127.0.0.1:{self.port}{repository_path}"

    def known_hosts_entry_name(self) -> str:
        return f"[127.0.0.1]:{self.port}"

    def is_pinned_in(self, known_hosts: Path) -> bool:
        """True if known_hosts trusts this server's host key (entries may be hashed)."""
        if not known_hosts.exists():
            return False
        result = subprocess.run(
            ["ssh-keygen", "-F", self.known_hosts_entry_name(), "-f", str(known_hosts)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and self.host_key_pub.split()[1] in result.stdout

    def log(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")
        except OSError:
            return ""

    def add_authorized_key(self, public_key: str, options: str = "") -> None:
        line = f"{options} {public_key.strip()}".strip()
        with open(self.authorized_keys, "a") as f:
            f.write(line + "\n")

    def start(self) -> None:
        sshd = find_sshd()
        assert sshd is not None
        if os.geteuid() == 0:
            # Debian's sshd refuses to start as root without its privilege
            # separation directory, which isn't created until the service runs.
            os.makedirs("/run/sshd", mode=0o755, exist_ok=True)

        config = self.root / "sshd_config"
        config.write_text(
            "\n".join(
                [
                    f"Port {self.port}",
                    "ListenAddress 127.0.0.1",
                    f"HostKey {self.root / 'host_key'}",
                    f"AuthorizedKeysFile {self.authorized_keys}",
                    f"PidFile {self.root / 'sshd.pid'}",
                    "PubkeyAuthentication yes",
                    "PasswordAuthentication no",
                    "KbdInteractiveAuthentication no",
                    "PermitRootLogin prohibit-password",
                    "UsePAM no",
                    # Temp directories aren't owned the way StrictModes expects
                    "StrictModes no",
                    "LogLevel VERBOSE",
                ]
            )
            + "\n"
        )
        log = open(self.log_path, "ab")
        self.process = subprocess.Popen(
            [sshd, "-D", "-e", "-f", str(config)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        log.close()
        self._wait_until_ready()

    def _wait_until_ready(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(f"sshd exited on startup:\n{self.log()}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1) as s:
                    if s.recv(4).startswith(b"SSH-"):
                        return
            except OSError:
                pass
            time.sleep(0.1)
        raise RuntimeError(f"sshd didn't start within {timeout}s:\n{self.log()}")

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None


def start_ssh_server(root: Path) -> SshServer:
    root.mkdir(parents=True, exist_ok=True)
    generate_key(root / "host_key")
    client_key = generate_key(root / "client_key")
    borg_path = shutil.which("borg")
    assert borg_path is not None

    server = SshServer(
        root=root,
        port=free_port(),
        user=getpass.getuser(),
        borg_path=borg_path,
        client_key=client_key,
        host_key_pub=(root / "host_key.pub").read_text().strip(),
    )
    server.add_authorized_key((root / "client_key.pub").read_text())
    server.start()
    return server
