"""
Tests for remote (ssh://) borg repository support.
"""

import importlib.util
import os
import shlex
import stat
import uuid
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterator
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import Repository
from borgitory.models.enums import EncryptionType
from borgitory.models.repository_dtos import (
    CreateRepositoryRequest,
    DeleteRepositoryRequest,
    ImportRepositoryRequest,
)
from borgitory.models.schemas import RepositoryCreate, RepositoryUpdate
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.repository_protocols import BackupServiceProtocol
from borgitory.models.job_results import JobStatusEnum, JobTypeEnum
from borgitory.services.jobs.job_models import (
    BorgJob,
    BorgJobTask,
    TaskStatusEnum,
    TaskTypeEnum,
)
from borgitory.services.jobs.task_executors.cloud_sync_task_executor import (
    CloudSyncTaskExecutor,
)
from borgitory.services.repositories.repository_environment import (
    build_repository_env_overrides,
    build_repository_env_overrides_from_data,
)
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.services.ssh import repository_ssh_service
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import (
    build_secure_borg_command_with_keyfile,
    is_remote_repository_path,
    sanitize_path,
    validate_remote_repository_url,
)

REMOTE_URL = "ssh://u123@u123.your-storagebox.de:23/./backups/repo"
PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\r\nabc\r\n-----END OPENSSH PRIVATE KEY-----"
)


@pytest.fixture(autouse=True)
def ssh_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(repository_ssh_service, "DATA_DIR", str(tmp_path))
    return tmp_path


def rsh_args(env: Dict[str, str]) -> list[str]:
    return shlex.split(env["BORG_RSH"])


class TestRemotePathValidation:
    @pytest.mark.parametrize(
        "url",
        [
            REMOTE_URL,
            "ssh://abcd1234@abcd1234.repo.borgbase.com/./repo",
            "ssh://borg@nas.local/srv/borg/repo",
        ],
    )
    def test_valid_urls(self, url: str) -> None:
        assert is_remote_repository_path(url)
        assert validate_remote_repository_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "ssh://host/./repo",  # missing user
            "ssh://user@host",  # missing path
            "ssh://user@host:99999/repo",  # port out of range
            "ssh://user@host/repo with space",
        ],
    )
    def test_invalid_urls(self, url: str) -> None:
        with pytest.raises(ValueError):
            validate_remote_repository_url(url)

    def test_local_paths_are_not_remote(self) -> None:
        assert not is_remote_repository_path("/repos/my-repo")
        assert not is_remote_repository_path("")
        assert not is_remote_repository_path(None)

    def test_sanitize_path_keeps_remote_url_intact(self) -> None:
        assert sanitize_path(REMOTE_URL) == REMOTE_URL
        assert sanitize_path(f"{REMOTE_URL}::archive-1") == f"{REMOTE_URL}::archive-1"

    def test_sanitize_path_still_rejects_injection_in_remote_url(self) -> None:
        with pytest.raises(ValueError):
            sanitize_path("ssh://u@h/$(reboot)")

    def test_sanitize_path_still_normalizes_local_paths(self) -> None:
        assert sanitize_path("/repos//a/./b") == "/repos/a/b"

    def test_schema_accepts_local_and_remote_paths(self) -> None:
        for path in ["/repos/a", REMOTE_URL]:
            repo = RepositoryCreate(
                name="r", path=path, encryption_type=EncryptionType.NONE
            )
            assert repo.path == path

    def test_schema_rejects_relative_path(self) -> None:
        with pytest.raises(ValidationError):
            RepositoryCreate(
                name="r", path="relative/repo", encryption_type=EncryptionType.NONE
            )

    def test_schema_rejects_unsafe_remote_borg_path(self) -> None:
        with pytest.raises(ValidationError):
            RepositoryCreate(
                name="r",
                path=REMOTE_URL,
                encryption_type=EncryptionType.NONE,
                remote_borg_path="borg; rm -rf /",
            )

    def test_update_schema_accepts_remote_path(self) -> None:
        update = RepositoryUpdate.model_validate({"path": REMOTE_URL})
        assert update.path == REMOTE_URL


class TestKeyfileCommandEnvironment:
    def test_keyfile_builder_keeps_caller_overrides(self) -> None:
        result = build_secure_borg_command_with_keyfile(
            base_command="borg info",
            repository_path="/tmp/repo",
            passphrase="secret",
            environment_overrides={
                "BORG_CACHE_DIR": "/cache",
                "BORG_RSH": "ssh -o BatchMode=yes",
            },
        )

        assert result.environment["BORG_CACHE_DIR"] == "/cache"
        assert result.environment["BORG_RSH"] == "ssh -o BatchMode=yes"
        assert result.environment["BORG_PASSPHRASE"] == "secret"


class TestSshEnvironment:
    def test_local_repository_has_no_ssh_env(self) -> None:
        assert (
            repository_ssh_service.build_ssh_env_overrides(
                1, "/repos/a", PRIVATE_KEY, "borg-1.4"
            )
            == {}
        )

    def test_remote_repository_with_key(self, ssh_data_dir: Path) -> None:
        env = repository_ssh_service.build_ssh_env_overrides(
            7, REMOTE_URL, PRIVATE_KEY, "borg-1.4"
        )

        key_path = ssh_data_dir / "ssh" / "keys" / "repo_7"
        args = rsh_args(env)
        assert args[0] == "ssh"
        assert args[args.index("-i") + 1] == str(key_path)
        assert "BatchMode=yes" in args
        assert "StrictHostKeyChecking=accept-new" in args
        assert f"UserKnownHostsFile={ssh_data_dir / 'ssh' / 'known_hosts'}" in args
        assert env["BORG_REMOTE_PATH"] == "borg-1.4"

        assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
        # CRLF from a pasted textarea is normalized and a trailing newline added
        assert key_path.read_text() == PRIVATE_KEY.replace("\r\n", "\n") + "\n"

    def test_remote_repository_without_key_uses_default_identity(self) -> None:
        env = repository_ssh_service.build_ssh_env_overrides(7, REMOTE_URL, None, None)

        assert "-i" not in rsh_args(env)
        assert "BORG_REMOTE_PATH" not in env

    def test_key_file_is_rewritten_when_key_changes(self, ssh_data_dir: Path) -> None:
        repository_ssh_service.build_ssh_env_overrides(3, REMOTE_URL, "old", None)
        repository_ssh_service.build_ssh_env_overrides(3, REMOTE_URL, "new", None)

        assert (ssh_data_dir / "ssh" / "keys" / "repo_3").read_text() == "new\n"

    def test_paths_with_spaces_are_quoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data_dir = tmp_path / "Application Support"
        monkeypatch.setattr(repository_ssh_service, "DATA_DIR", str(data_dir))

        env = repository_ssh_service.build_ssh_env_overrides(
            1, REMOTE_URL, PRIVATE_KEY, None
        )

        args = rsh_args(env)
        assert args[args.index("-i") + 1] == str(data_dir / "ssh" / "keys" / "repo_1")

    def test_windows_paths_are_translated_for_wsl(self) -> None:
        assert (
            repository_ssh_service._to_executor_path(
                "C:\\Users\\me\\AppData\\Local\\Borgitory\\ssh\\known_hosts"
            )
            == "/mnt/c/Users/me/AppData/Local/Borgitory/ssh/known_hosts"
        )

    def test_delete_key_file(self, ssh_data_dir: Path) -> None:
        repository_ssh_service.write_key_file(5, PRIVATE_KEY)
        repository_ssh_service.delete_key_file(5)
        repository_ssh_service.delete_key_file(5)  # missing file is fine

        assert not (ssh_data_dir / "ssh" / "keys" / "repo_5").exists()

    def test_env_from_repository_model(self) -> None:
        repository = Repository()
        repository.id = 9
        repository.path = REMOTE_URL
        repository.cache_dir = "/cache"
        repository.set_ssh_private_key(PRIVATE_KEY)
        repository.remote_borg_path = "borg-1.4"

        env = build_repository_env_overrides(repository)

        assert env["BORG_CACHE_DIR"] == "/cache"
        assert "-i" in rsh_args(env)
        assert env["BORG_REMOTE_PATH"] == "borg-1.4"

    def test_env_from_repository_data(self) -> None:
        env = build_repository_env_overrides_from_data(
            {
                "id": 9,
                "path": REMOTE_URL,
                "cache_dir": None,
                "ssh_private_key": PRIVATE_KEY,
                "remote_borg_path": None,
            }
        )

        assert "BORG_CACHE_DIR" not in env
        assert "-i" in rsh_args(env)

    def test_env_from_local_repository_data(self) -> None:
        assert build_repository_env_overrides_from_data(
            {"id": 1, "path": "/repos/a", "cache_dir": "/cache"}
        ) == {"BORG_CACHE_DIR": "/cache"}


class TestRepositoryModel:
    def test_ssh_private_key_is_encrypted_at_rest(self) -> None:
        repository = Repository()
        repository.set_ssh_private_key(PRIVATE_KEY)

        assert repository.encrypted_ssh_private_key is not None
        assert PRIVATE_KEY not in repository.encrypted_ssh_private_key
        assert repository.get_ssh_private_key() == PRIVATE_KEY

        repository.set_ssh_private_key(None)
        assert repository.encrypted_ssh_private_key is None

    def test_is_remote(self) -> None:
        repository = Repository()
        repository.path = REMOTE_URL
        assert repository.is_remote
        repository.path = "/repos/a"
        assert not repository.is_remote


class TestRepositoryServiceRemote:
    @pytest.fixture
    def mock_borg_service(self) -> Mock:
        mock = Mock(spec=BackupServiceProtocol)
        mock.initialize_repository = AsyncMock()
        mock.verify_repository_access = AsyncMock()
        mock.list_archives = AsyncMock()
        return mock

    @pytest.fixture
    def repository_service(self, mock_borg_service: Mock) -> RepositoryService:
        command_executor = Mock(spec=CommandExecutorProtocol)
        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=Mock(remove_schedule=AsyncMock()),
            path_service=Mock(),
            command_executor=command_executor,
            file_service=Mock(),
        )

    async def test_create_remote_repository_writes_key_before_borg_runs(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: AsyncSession,
    ) -> None:
        seen_env: Dict[str, str] = {}

        async def init(repo: Repository) -> Mock:
            seen_env.update(build_repository_env_overrides(repo))
            return Mock(success=True, message="ok")

        mock_borg_service.initialize_repository.side_effect = init

        result = await repository_service.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=REMOTE_URL,
                encryption_type=EncryptionType.REPOKEY,
                passphrase="secret123",
                ssh_private_key=PRIVATE_KEY,
                remote_borg_path="borg-1.4",
            ),
            test_db,
        )

        assert result.success is True
        args = rsh_args(seen_env)
        assert Path(args[args.index("-i") + 1]).exists()
        assert seen_env["BORG_REMOTE_PATH"] == "borg-1.4"

        saved = (
            await test_db.execute(select(Repository).where(Repository.name == "remote"))
        ).scalar_one()
        assert saved.path == REMOTE_URL
        assert saved.get_ssh_private_key() == PRIVATE_KEY
        assert saved.remote_borg_path == "borg-1.4"

    async def test_failed_remote_create_rolls_back_and_removes_key(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: AsyncSession,
        ssh_data_dir: Path,
    ) -> None:
        async def init(repo: Repository) -> Mock:
            build_repository_env_overrides(repo)  # materializes the key file
            return Mock(
                success=False,
                message="Remote: Permission denied (publickey).\nConnection closed by remote host",
            )

        mock_borg_service.initialize_repository.side_effect = init

        result = await repository_service.create_repository(
            CreateRepositoryRequest(
                name="remote",
                path=REMOTE_URL,
                encryption_type=EncryptionType.NONE,
                ssh_private_key=PRIVATE_KEY,
            ),
            test_db,
        )

        assert result.success is False
        assert result.error_message is not None
        assert "SSH authentication failed" in result.error_message
        assert (
            await test_db.execute(select(Repository).where(Repository.name == "remote"))
        ).scalar_one_or_none() is None
        assert list((ssh_data_dir / "ssh" / "keys").iterdir()) == []

    async def test_ssh_settings_ignored_for_local_repository(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: AsyncSession,
    ) -> None:
        mock_borg_service.initialize_repository.return_value = Mock(
            success=True, message="ok"
        )

        await repository_service.create_repository(
            CreateRepositoryRequest(
                name="local",
                path="/repos/local",
                encryption_type=EncryptionType.NONE,
                ssh_private_key=PRIVATE_KEY,
                remote_borg_path="borg-1.4",
            ),
            test_db,
        )

        saved = (
            await test_db.execute(select(Repository).where(Repository.name == "local"))
        ).scalar_one()
        assert saved.encrypted_ssh_private_key is None
        assert saved.remote_borg_path is None

    async def test_import_remote_repository_failure_mentions_ssh(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: AsyncSession,
    ) -> None:
        mock_borg_service.verify_repository_access.return_value = False

        result = await repository_service.import_repository(
            ImportRepositoryRequest(
                name="remote",
                path=REMOTE_URL,
                encryption_type=EncryptionType.NONE,
                ssh_private_key=PRIVATE_KEY,
            ),
            test_db,
        )

        assert result.success is False
        assert result.error_message is not None
        assert "SSH private key" in result.error_message
        assert (
            await test_db.execute(select(Repository).where(Repository.name == "remote"))
        ).scalar_one_or_none() is None

    async def test_update_and_clear_ssh_key(
        self,
        repository_service: RepositoryService,
        test_db: AsyncSession,
        ssh_data_dir: Path,
    ) -> None:
        repository = Repository()
        repository.name = "remote"
        repository.path = REMOTE_URL
        repository.set_ssh_private_key("old")
        test_db.add(repository)
        await test_db.commit()
        await test_db.refresh(repository)
        repository_ssh_service.write_key_file(repository.id, "old")

        # Empty key keeps the current one; remote_borg_path is updated
        await repository_service.update_repository(
            repository.id,
            RepositoryUpdate.model_validate(
                {"ssh_private_key": "", "remote_borg_path": "borg-1.4"}
            ),
            test_db,
        )
        await test_db.refresh(repository)
        assert repository.get_ssh_private_key() == "old"
        assert repository.remote_borg_path == "borg-1.4"

        await repository_service.update_repository(
            repository.id,
            RepositoryUpdate.model_validate({"ssh_private_key": "new"}),
            test_db,
        )
        await test_db.refresh(repository)
        assert repository.get_ssh_private_key() == "new"

        await repository_service.update_repository(
            repository.id,
            RepositoryUpdate.model_validate(
                {"clear_ssh_private_key": "on", "remote_borg_path": ""}
            ),
            test_db,
        )
        await test_db.refresh(repository)
        assert repository.encrypted_ssh_private_key is None
        assert repository.remote_borg_path is None
        assert not (ssh_data_dir / "ssh" / "keys" / f"repo_{repository.id}").exists()

    async def test_delete_removes_key_file(
        self,
        repository_service: RepositoryService,
        test_db: AsyncSession,
        ssh_data_dir: Path,
    ) -> None:
        repository = Repository()
        repository.name = "remote"
        repository.path = REMOTE_URL
        test_db.add(repository)
        await test_db.commit()
        await test_db.refresh(repository)
        key_path = Path(repository_ssh_service.write_key_file(repository.id, "k"))

        result = await repository_service.delete_repository(
            DeleteRepositoryRequest(repository_id=repository.id), test_db
        )

        assert result.success is True
        assert not key_path.exists()

    @pytest.mark.parametrize(
        "borg_error,expected",
        [
            ("Host key verification failed.", "host key verification failed"),
            ("ssh: connect to host x port 23: Connection refused", "Could not connect"),
            ("Remote: bash: line 1: borg: command not found", "remote borg path"),
            ("ssh: Could not resolve hostname nope", "resolve"),
        ],
    )
    def test_ssh_error_messages(
        self, repository_service: RepositoryService, borg_error: str, expected: str
    ) -> None:
        assert expected in repository_service._parse_borg_initialization_error(
            borg_error
        )


class TestCloudSyncSkipsRemote:
    async def test_cloud_sync_skipped_for_remote_repository(self) -> None:
        database_manager = Mock()
        database_manager.get_repository_data = AsyncMock(
            return_value={"id": 1, "path": REMOTE_URL, "passphrase": "secret123"}
        )
        job_executor = Mock()
        job_executor.execute_cloud_sync_task = AsyncMock()
        executor = CloudSyncTaskExecutor(
            job_executor=job_executor,
            output_manager=Mock(add_output_line=AsyncMock()),
            event_broadcaster=Mock(),
            session_maker=Mock(),
            cloud_sync_service=Mock(),
            database_manager=database_manager,
        )
        task = BorgJobTask(
            task_type=TaskTypeEnum.CLOUD_SYNC,
            task_name="sync",
            parameters={"cloud_sync_config_id": 1},
        )
        job = BorgJob(
            id=uuid.uuid4(),
            job_type=JobTypeEnum.COMPOSITE,
            status=JobStatusEnum.RUNNING,
            started_at=now_utc(),
            tasks=[task],
            repository_id=1,
        )

        assert await executor.execute_cloud_sync_task(job, task) is True
        assert task.status == TaskStatusEnum.COMPLETED
        job_executor.execute_cloud_sync_task.assert_not_called()


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src/borgitory/alembic/versions/c3f1a7d2b9e4_add_remote_ssh_fields_to_repositories.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_c3f1a7d2b9e4", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration:
    @pytest.fixture
    def engine(self) -> Iterator[sa.Engine]:
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE repositories ("
                    "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, path VARCHAR NOT NULL)"
                )
            )
            conn.execute(
                sa.text("INSERT INTO repositories (name, path) VALUES ('r', '/r')")
            )
        yield engine
        engine.dispose()

    @staticmethod
    def run(engine: sa.Engine, direction: str) -> None:
        migration = load_migration()
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                getattr(migration, direction)()

    @staticmethod
    def columns(engine: sa.Engine) -> set[str]:
        return {c["name"] for c in sa.inspect(engine).get_columns("repositories")}

    def test_upgrade_and_downgrade(self, engine: sa.Engine) -> None:
        self.run(engine, "upgrade")
        assert {"encrypted_ssh_private_key", "remote_borg_path"} <= self.columns(engine)

        self.run(engine, "downgrade")
        assert "encrypted_ssh_private_key" not in self.columns(engine)
        assert "remote_borg_path" not in self.columns(engine)
        with engine.connect() as conn:
            assert (
                conn.execute(sa.text("SELECT path FROM repositories")).scalar() == "/r"
            )
