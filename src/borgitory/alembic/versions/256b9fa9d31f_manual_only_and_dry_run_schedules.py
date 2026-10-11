"""Manual only and dry run schedules

Revision ID: 256b9fa9d31f
Revises: 2628b151e709
Create Date: 2026-10-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "256b9fa9d31f"
down_revision: Union[str, Sequence[str], None] = "2628b151e709"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column(
            "cron_expression", existing_type=sa.VARCHAR(), nullable=True
        )
        batch_op.add_column(
            sa.Column(
                "dry_run", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Manual-only schedules have no cron; give them a placeholder and disable them
    # so they don't start running automatically after the downgrade.
    op.execute(
        "UPDATE schedules SET cron_expression = '0 2 * * *', enabled = 0 "
        "WHERE cron_expression IS NULL"
    )
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_column("dry_run")
        batch_op.alter_column(
            "cron_expression", existing_type=sa.VARCHAR(), nullable=False
        )
