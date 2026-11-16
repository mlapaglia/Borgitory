"""Add notify_on policy to notification configs

Revision ID: a4c2e8f1b7d3
Revises: c3f1a7d2b9e4
Create Date: 2026-11-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4c2e8f1b7d3"
down_revision: Union[str, Sequence[str], None] = "c3f1a7d2b9e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("notification_configs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("notify_on", sa.String(), nullable=False, server_default="all")
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("notification_configs", schema=None) as batch_op:
        batch_op.drop_column("notify_on")
