"""Multiple source paths for schedules

Revision ID: 1bf41c3dc043
Revises: 8390ab2be88a
Create Date: 2026-10-11 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1bf41c3dc043"
down_revision: Union[str, Sequence[str], None] = "8390ab2be88a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source_paths", sa.JSON(), nullable=False, server_default="[]")
        )

    # Empty source_path meant maintenance-only; that becomes an empty list.
    op.execute(
        "UPDATE schedules SET source_paths = json_array(trim(source_path)) "
        "WHERE source_path IS NOT NULL AND trim(source_path) != ''"
    )

    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("source_path")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source_path", sa.String(), nullable=False, server_default="")
        )

    # Only a single path can be represented; keep the first one.
    op.execute(
        "UPDATE schedules SET source_path = coalesce(json_extract(source_paths, '$[0]'), '')"
    )

    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("source_paths")
