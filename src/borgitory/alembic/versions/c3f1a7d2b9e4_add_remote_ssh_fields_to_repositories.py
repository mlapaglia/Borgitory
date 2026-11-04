"""Add remote SSH fields to repositories table

Revision ID: c3f1a7d2b9e4
Revises: 1bf41c3dc043
Create Date: 2026-10-11 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f1a7d2b9e4"
down_revision: Union[str, Sequence[str], None] = "1bf41c3dc043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("repositories", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("encrypted_ssh_private_key", sa.Text(), nullable=True)
        )
        batch_op.add_column(sa.Column("remote_borg_path", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("repositories", schema=None) as batch_op:
        batch_op.drop_column("remote_borg_path")
        batch_op.drop_column("encrypted_ssh_private_key")
