"""Per-repository environment variables passed to every borg invocation."""

from typing import Mapping, Optional

from borgitory.models.database import Repository
from borgitory.services.ssh.repository_ssh_service import build_ssh_env_overrides


def _build_env_overrides(
    repository_id: Optional[int],
    path: Optional[str],
    cache_dir: Optional[str],
    ssh_private_key: Optional[str],
    remote_borg_path: Optional[str],
) -> dict[str, str]:
    env_overrides: dict[str, str] = {}
    if cache_dir:
        env_overrides["BORG_CACHE_DIR"] = cache_dir
    env_overrides.update(
        build_ssh_env_overrides(repository_id, path, ssh_private_key, remote_borg_path)
    )
    return env_overrides


def build_repository_env_overrides(repository: Repository) -> dict[str, str]:
    """Build environment overrides (cache dir, SSH) for a repository model."""
    return _build_env_overrides(
        repository.id,
        repository.path,
        repository.cache_dir,
        repository.get_ssh_private_key(),
        repository.remote_borg_path,
    )


def build_repository_env_overrides_from_data(
    repo_data: Mapping[str, object],
) -> dict[str, str]:
    """Build environment overrides from the dict returned by get_repository_data."""

    def _str(key: str) -> Optional[str]:
        value = repo_data.get(key)
        return value if isinstance(value, str) and value else None

    repo_id = repo_data.get("id")
    return _build_env_overrides(
        repo_id if isinstance(repo_id, int) else None,
        _str("path"),
        _str("cache_dir"),
        _str("ssh_private_key"),
        _str("remote_borg_path"),
    )
