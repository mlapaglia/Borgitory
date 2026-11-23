"""Add compression to schedules

Lets a scheduled backup pick its compression algorithm, like a manual backup.
Existing schedules keep the previous hard-coded behavior (zstd).

Revision ID: f7c2e9a4b1d3
Revises: e5b8d2a7c4f9
Create Date: 2026-11-23 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7c2e9a4b1d3"
down_revision: Union[str, Sequence[str], None] = "e5b8d2a7c4f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("compression", sa.String(), nullable=False, server_default="zstd")
        )


def downgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("compression")
