"""Add schedule retry and timeout fields

Revision ID: 4d6f8f8a9c21
Revises: 18b9095bc772
Create Date: 2026-05-22 03:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d6f8f8a9c21"
down_revision: Union[str, Sequence[str], None] = "18b9095bc772"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("backup_timeout_seconds", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "backup_retry_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column("cloud_sync_timeout_seconds", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "cloud_sync_retry_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("cloud_sync_retry_count")
        batch_op.drop_column("cloud_sync_timeout_seconds")
        batch_op.drop_column("backup_retry_count")
        batch_op.drop_column("backup_timeout_seconds")
