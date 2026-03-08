"""Rename source_path to source_paths and convert data to JSON arrays

Revision ID: a1b2c3d4e5f6
Revises: 2628b151e709
Create Date: 2026-03-07 00:00:00.000000

"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2628b151e709"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename source_path to source_paths and convert plain strings to JSON arrays."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column("source_path", new_column_name="source_paths")

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_paths FROM schedules")
    ).fetchall()

    for row in rows:
        row_id, value = row[0], row[1]
        if value is None or not value.strip():
            new_value = "[]"
        elif value.strip().startswith("["):
            new_value = value
        else:
            new_value = json.dumps([value.strip()])

        connection.execute(
            sa.text("UPDATE schedules SET source_paths = :val WHERE id = :id"),
            {"val": new_value, "id": row_id},
        )


def downgrade() -> None:
    """Rename source_paths back to source_path and convert JSON arrays to plain strings."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, source_paths FROM schedules")
    ).fetchall()

    for row in rows:
        row_id, value = row[0], row[1]
        if value and value.strip().startswith("["):
            try:
                paths = json.loads(value)
                new_value = paths[0] if paths else "/data"
            except json.JSONDecodeError, IndexError:
                new_value = "/data"
        else:
            new_value = value or "/data"

        connection.execute(
            sa.text("UPDATE schedules SET source_paths = :val WHERE id = :id"),
            {"val": new_value, "id": row_id},
        )

    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column("source_paths", new_column_name="source_path")
