"""
Tests for the migration that converts schedules.source_path into a source_paths list.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterator

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "src/borgitory/alembic/versions/1bf41c3dc043_multiple_source_paths_for_schedules.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_1bf41c3dc043", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load_migration()


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE schedules ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
                "source_path VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO schedules (name, source_path) VALUES "
                "('backup', '/data'), ('padded', '  /padded  '), "
                "('maintenance', ''), ('blank', '   ')"
            )
        )
    yield engine
    engine.dispose()


def run(engine: sa.Engine, direction: str) -> None:
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def columns(engine: sa.Engine) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns("schedules")}


def rows(engine: sa.Engine, column: str) -> Dict[str, str]:
    with engine.connect() as conn:
        result = conn.execute(sa.text(f"SELECT name, {column} FROM schedules"))
        return {name: value for name, value in result}


def test_upgrade_converts_source_path_to_list(engine: sa.Engine) -> None:
    run(engine, "upgrade")

    assert "source_path" not in columns(engine)
    source_paths = {
        name: json.loads(value) for name, value in rows(engine, "source_paths").items()
    }
    assert source_paths == {
        "backup": ["/data"],
        "padded": ["/padded"],
        "maintenance": [],
        "blank": [],
    }


def test_downgrade_keeps_first_path(engine: sa.Engine) -> None:
    run(engine, "upgrade")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                'UPDATE schedules SET source_paths = \'["/a", "/b"]\' '
                "WHERE name = 'backup'"
            )
        )

    run(engine, "downgrade")

    assert "source_paths" not in columns(engine)
    assert rows(engine, "source_path") == {
        "backup": "/a",
        "padded": "/padded",
        "maintenance": "",
        "blank": "",
    }
