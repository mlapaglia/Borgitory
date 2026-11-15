"""
End-to-end tests for remote (ssh://) repositories against a real sshd and borg.

These start a throwaway OpenSSH server (see tests/integration/ssh_server.py) and
drive the real repository/borg services, so the BORG_RSH command line, key
files, known_hosts handling and error parsing are exercised by ssh itself rather
than by assertions on the strings we generate. They skip when sshd, ssh,
ssh-keygen or borg isn't installed.
"""

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Iterator
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from borgitory.config.command_runner_config import CommandRunnerConfig
from borgitory.models.database import Base, Repository
from borgitory.models.enums import EncryptionType
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.models.repository_dtos import (
    CreateRepositoryRequest,
    ImportRepositoryRequest,
    RepositoryOperationResult,
)
from borgitory.services.borg_service import BorgService
from borgitory.services.command_execution.linux_command_executor import (
    LinuxCommandExecutor,
)
from borgitory.services.jobs.job_database_manager import JobDatabaseManager
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.services.jobs.task_executors.backup_task_executor import (
    BackupTaskExecutor,
)
from borgitory.services.path.path_service import PathService
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.ssh import repository_ssh_service
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import validate_remote_repository_url
from tests.integration.ssh_server import (
    SshServer,
    generate_key,
    missing_tools,
    start_ssh_server,
)

PASSPHRASE = "remote-test-passphrase"

pytestmark = [
    pytest.mark.skipif(
        sys.platform == "win32", reason="needs sshd and borg (run inside WSL)"
    ),
    pytest.mark.skipif(
        bool(missing_tools()),
        reason=f"remote repository tests need: {', '.join(missing_tools())}",
    ),
]


@pytest.fixture(scope="module")
def ssh_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SshServer]:
    server = start_ssh_server(tmp_path_factory.mktemp("sshd"))
    yield server
    server.stop()


@pytest.fixture(autouse=True)
def sshd_log(ssh_server: SshServer) -> Iterator[None]:
    """Print this test's sshd log; pytest only shows it when the test fails."""
    log_size = len(ssh_server.log())
    yield
    print(f"--- sshd log ---\n{ssh_server.log()[log_size:]}")


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Borgitory's data dir (SSH keys, known_hosts) and an isolated borg home."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(repository_ssh_service, "DATA_DIR", str(data))
    monkeypatch.setenv("BORG_BASE_DIR", str(tmp_path / "borg-home"))
    return data


@pytest.fixture
def repos_dir(tmp_path: Path) -> Path:
    path = tmp_path / "repos"
    path.mkdir()
    return path


@pytest_asyncio.fixture
async def session_maker(
    tmp_path: Path,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'borgitory.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@dataclass
class Services:
    executor: LinuxCommandExecutor
    borg: BorgService
    repositories: RepositoryService


@pytest.fixture
def services() -> Services:
    executor = LinuxCommandExecutor()
    path_service = PathService(executor)
    borg = BorgService(
        job_executor=JobExecutor(executor),
        command_runner=SimpleCommandRunner(CommandRunnerConfig(), executor),
        # Remote verification must not go through the job manager (it blocks)
        job_manager=Mock(),
        archive_service=Mock(),
        command_executor=executor,
        path_service=path_service,
    )
    repositories = RepositoryService(
        borg_service=borg,
        scheduler_service=Mock(remove_schedule=AsyncMock()),
        path_service=path_service,
        command_executor=executor,
        file_service=Mock(),
    )
    return Services(executor=executor, borg=borg, repositories=repositories)


def init_on_server(server: SshServer, data_dir: Path, repository_path: Path) -> str:
    """Create a repository on the server with the borg CLI, for import tests."""
    url = server.url(repository_path)
    env = {
        **os.environ,
        "BORG_PASSPHRASE": PASSPHRASE,
        **repository_ssh_service.build_ssh_env_overrides(
            99_999, url, server.client_key, server.borg_path
        ),
    }
    subprocess.run(
        ["borg", "init", "--encryption=repokey", url],
        env=env,
        check=True,
        capture_output=True,
    )
    repository_ssh_service.delete_key_file(99_999)
    return url


def keys_left_on_disk(data_dir: Path) -> list[str]:
    keys_dir = data_dir / "ssh" / "keys"
    return sorted(p.name for p in keys_dir.iterdir()) if keys_dir.exists() else []


async def get_repository(
    session_maker: async_sessionmaker[AsyncSession], name: str
) -> Repository:
    async with session_maker() as db:
        return (
            await db.execute(select(Repository).where(Repository.name == name))
        ).scalar_one()


async def test_create_backup_and_list_remote_repository(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    url = validate_remote_repository_url(ssh_server.url(repos_dir / "repo"))

    async with session_maker() as db:
        result = await services.repositories.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=url,
                encryption_type=EncryptionType.REPOKEY,
                passphrase=PASSPHRASE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )

    assert result.success, result.error_message
    assert (repos_dir / "repo" / "config").exists()
    # The host key was pinned on first use, and the pending key file is gone
    assert ssh_server.is_pinned_in(data_dir / "ssh" / "known_hosts")
    assert keys_left_on_disk(data_dir) == []

    repository = await get_repository(session_maker, "remote")

    # Back up through the real backup task executor, which builds its SSH
    # environment from the job database's repository data
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("hello from a remote backup\n")
    task = BorgJobTask(
        task_type=TaskTypeEnum.BACKUP,
        task_name="Backup",
        parameters={"source_paths": [str(source)], "archive_name": "first"},
    )
    job = BorgJob(
        id=uuid.uuid4(),
        job_type=JobTypeEnum.COMPOSITE,
        status=JobStatusEnum.RUNNING,
        started_at=now_utc(),
        tasks=[task],
        repository_id=repository.id,
    )
    backup_executor = BackupTaskExecutor(
        job_executor=JobExecutor(services.executor),
        output_manager=Mock(add_output_line=AsyncMock()),
        event_broadcaster=Mock(),
        database_manager=JobDatabaseManager(session_maker),
    )

    assert await backup_executor.execute_backup_task(job, task), task.error
    assert task.status == TaskStatusEnum.COMPLETED
    assert keys_left_on_disk(data_dir) == [f"repo_{repository.id}"]

    archives = await services.borg.list_archives(repository)
    assert [archive.name for archive in archives.archives] == ["first"]

    info = await services.repositories.get_repository_info(repository)
    assert info["success"], info
    assert info["config_error"] is None
    assert "remote repositories" in info["config_unavailable"]


async def test_import_remote_repository(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    url = init_on_server(ssh_server, data_dir, repos_dir / "existing")

    async with session_maker() as db:
        result = await services.repositories.import_repository(
            ImportRepositoryRequest(
                name="imported",
                path=url,
                encryption_type=EncryptionType.REPOKEY,
                passphrase=PASSPHRASE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )

    assert result.success, result.error_message
    assert keys_left_on_disk(data_dir) == []


async def test_concurrent_imports_with_the_same_key(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_url = init_on_server(ssh_server, data_dir, repos_dir / "first")
    second_url = init_on_server(ssh_server, data_dir, repos_dir / "second")
    first_done = asyncio.Event()

    # Force the race: the second import has written its key file and built its
    # ssh command, but borg doesn't start until the first import has finished
    # and cleaned up after itself.
    execute_command = services.executor.execute_command

    async def delayed_execute_command(
        command: list[str], *args: Any, **kwargs: Any
    ) -> Any:
        if second_url in command:
            await first_done.wait()
        return await execute_command(command, *args, **kwargs)

    monkeypatch.setattr(services.executor, "execute_command", delayed_execute_command)

    async def import_repository(name: str, url: str) -> RepositoryOperationResult:
        async with session_maker() as db:
            return await services.repositories.import_repository(
                ImportRepositoryRequest(
                    name=name,
                    path=url,
                    encryption_type=EncryptionType.REPOKEY,
                    passphrase=PASSPHRASE,
                    ssh_private_key=ssh_server.client_key,
                    remote_borg_path=ssh_server.borg_path,
                ),
                db,
            )

    async def import_first() -> RepositoryOperationResult:
        try:
            return await import_repository("first", first_url)
        finally:
            first_done.set()

    first, second = await asyncio.gather(
        import_first(), import_repository("second", second_url)
    )

    # Finishing the first import must not delete the second one's identity file
    assert first.success, first.error_message
    assert second.success, second.error_message
    assert keys_left_on_disk(data_dir) == []


async def test_lock_status_over_ssh(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    url = init_on_server(ssh_server, data_dir, repos_dir / "repo")
    async with session_maker() as db:
        result = await services.repositories.import_repository(
            ImportRepositoryRequest(
                name="remote",
                path=url,
                encryption_type=EncryptionType.REPOKEY,
                passphrase=PASSPHRASE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )
    assert result.success, result.error_message
    repository = await get_repository(session_maker, "remote")

    status = await services.repositories.check_repository_lock_status(repository)
    assert status == {
        "locked": False,
        "accessible": True,
        "message": "Repository is accessible",
    }

    # Hold the repository lock from another borg process
    env = {
        **os.environ,
        "BORG_PASSPHRASE": PASSPHRASE,
        **repository_ssh_service.build_ssh_env_overrides(
            repository.id, url, ssh_server.client_key, ssh_server.borg_path
        ),
    }
    holder = subprocess.Popen(
        ["borg", "with-lock", url, "sleep", "30"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = await services.repositories.check_repository_lock_status(
                repository
            )
            if status["locked"]:
                break
            assert holder.poll() is None, holder.stderr.read() if holder.stderr else ""
            await asyncio.sleep(0.5)
        assert status["locked"] is True, status
    finally:
        holder.terminate()
        holder.wait(timeout=10)


async def test_rejected_key_reports_ssh_authentication_failure(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    unauthorized_key = generate_key(tmp_path / "unauthorized")

    async with session_maker() as db:
        result = await services.repositories.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=ssh_server.url(repos_dir / "repo"),
                encryption_type=EncryptionType.NONE,
                ssh_private_key=unauthorized_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )

    assert result.success is False
    assert result.error_message is not None
    assert "SSH authentication failed" in result.error_message
    assert keys_left_on_disk(data_dir) == []
    async with session_maker() as db:
        assert (await db.execute(select(Repository))).scalars().all() == []


async def test_changed_host_key_is_refused(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    generate_key(tmp_path / "other_host_key")
    other_host_key = (tmp_path / "other_host_key.pub").read_text().strip()
    (data_dir / "ssh").mkdir()
    (data_dir / "ssh" / "known_hosts").write_text(
        f"{ssh_server.known_hosts_entry_name()} {other_host_key}\n"
    )

    async with session_maker() as db:
        result = await services.repositories.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=ssh_server.url(repos_dir / "repo"),
                encryption_type=EncryptionType.NONE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )

    assert result.success is False
    assert result.error_message is not None
    assert "host key verification failed" in result.error_message
    assert not (repos_dir / "repo").exists()


async def test_missing_remote_borg_is_reported(
    ssh_server: SshServer,
    data_dir: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as db:
        result = await services.repositories.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=ssh_server.url(repos_dir / "repo"),
                encryption_type=EncryptionType.NONE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path="borg-not-installed-here",
            ),
            db,
        )

    assert result.success is False
    assert result.error_message is not None
    assert "Borg was not found on the remote server" in result.error_message


async def test_data_dir_with_spaces(
    ssh_server: SshServer,
    tmp_path: Path,
    repos_dir: Path,
    services: Services,
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "Application Support" / "Borgitory"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr(repository_ssh_service, "DATA_DIR", str(data_dir))
    monkeypatch.setenv("BORG_BASE_DIR", str(tmp_path / "borg-home"))

    async with session_maker() as db:
        result = await services.repositories.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=ssh_server.url(repos_dir / "repo"),
                encryption_type=EncryptionType.NONE,
                ssh_private_key=ssh_server.client_key,
                remote_borg_path=ssh_server.borg_path,
            ),
            db,
        )

    assert result.success, result.error_message
    # ssh wrote the pinned host key to the quoted path, not a truncated one
    assert ssh_server.is_pinned_in(data_dir / "ssh" / "known_hosts")
    assert not (tmp_path / "Application").exists()


@pytest.fixture
def unresponsive_server() -> Iterator[int]:
    """A TCP port that accepts connections but never sends an SSH banner."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    accepted: list[socket.socket] = []

    def accept_loop() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            accepted.append(connection)

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    yield int(listener.getsockname()[1])
    listener.close()
    for connection in accepted:
        connection.close()


async def test_unresponsive_server_does_not_hang_verification(
    unresponsive_server: int,
    data_dir: Path,
    services: Services,
    ssh_server: SshServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repository_ssh_service, "SSH_CONNECT_TIMEOUT_SECONDS", 2)
    repository = Repository()
    repository.name = "stalled"
    repository.path = f"ssh://{ssh_server.user}@127.0.0.1:{unresponsive_server}/repo"
    repository.set_ssh_private_key(ssh_server.client_key)
    repository.remote_borg_path = ssh_server.borg_path
    repository.pending_ssh_key_token = repository_ssh_service.new_pending_key_token()

    started = time.monotonic()
    assert await services.borg.verify_repository_access(repository) is False
    assert time.monotonic() - started < 20
