"""Add source_paths_json column; backfill from source_path (string). source_path kept as deprecated.

Revision ID: b2c3d4e5f6a7
Revises: 2628b151e709
Create Date: 2026-03-07 00:00:00.000000

"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "2628b151e709"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _string_to_paths_list(value: str | None) -> list[str]:
    if value is None or not value or not str(value).strip():
        return []
    s = str(value).strip()
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, str) and p.strip()]
            return []
        except json.JSONDecodeError, ValueError:
            return []
    return [s]


def upgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_paths_json", sa.JSON(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_path FROM schedules")
    ).fetchall()

    for row in rows:
        row_id, value = row[0], row[1]
        paths = _string_to_paths_list(value)
        conn_val = json.dumps(paths) if paths else "[]"
        connection.execute(
            sa.text("UPDATE schedules SET source_paths_json = :val WHERE id = :id"),
            {"val": conn_val, "id": row_id},
        )

    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column(
            "source_paths_json",
            existing_type=sa.JSON(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("source_paths_json")
