"""
The ORM models and the Alembic migrations must describe the same schema.

Tests build their schema with ``Base.metadata.create_all``, while production
runs ``alembic upgrade head``. Without this check a model change that lacks a
migration passes every test and only fails on a user's upgrade.
"""

from pathlib import Path
from typing import Any, Optional

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import borgitory
from borgitory.models.database import Base

ALEMBIC_DIR = Path(borgitory.__file__).parent / "alembic"


def _include_object(
    obj: Any, name: Optional[str], type_: str, reflected: bool, compare_to: Any
) -> bool:
    # APScheduler manages its own table; mirrors alembic/env.py
    return not (name and "apscheduler" in name.lower())


def _alembic_config() -> Config:
    # Built in code (no ini file) so env.py doesn't reconfigure global logging
    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    return cfg


@pytest.fixture
def migrated_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    # env.py prefers ./local-data/borgitory.db when present; never touch it
    monkeypatch.chdir(tmp_path)
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic_config(), "head")
    return url


def test_single_migration_head() -> None:
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1, f"Multiple Alembic heads, merge them: {heads}"


def test_models_match_migrations(migrated_db_url: str) -> None:
    engine = create_engine(migrated_db_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "include_object": _include_object},
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], (
        "Models and migrations have drifted. Generate a migration with "
        "`alembic revision --autogenerate`:\n" + "\n".join(map(str, diff))
    )


def test_downgrade_to_base_and_back(migrated_db_url: str) -> None:
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_session_token_hash_migration_preserves_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import text

    from borgitory.utils.web_security import hash_session_token

    monkeypatch.chdir(tmp_path)
    url = f"sqlite:///{tmp_path / 'sessions.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config()
    command.upgrade(cfg, "c3f1a7d2b9e4")  # revision before hashing

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, created_at) "
                    "VALUES (1, 'u', 'x', CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO user_sessions (user_id, session_token, expires_at, "
                    "remember_me, created_at, last_activity) VALUES "
                    "(1, 'plain-token', CURRENT_TIMESTAMP, 0, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)"
                )
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            stored = conn.execute(text("SELECT session_token FROM user_sessions"))
            assert stored.scalar_one() == hash_session_token("plain-token")
    finally:
        engine.dispose()
