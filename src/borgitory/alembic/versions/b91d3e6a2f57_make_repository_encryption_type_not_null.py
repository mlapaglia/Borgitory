"""Make repositories.encryption_type NOT NULL to match the model

The column was added as nullable (02b7b29d38c0) and backfilled, but the model
has always declared it NOT NULL. Detected by the model/migration drift test.

Revision ID: b91d3e6a2f57
Revises: a7e2c4f1d8b3
Create Date: 2026-11-16 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b91d3e6a2f57"
down_revision: Union[str, Sequence[str], None] = "a7e2c4f1d8b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Same backfill value as the migration that introduced the column
    op.execute(
        "UPDATE repositories SET encryption_type = 'repokey' "
        "WHERE encryption_type IS NULL"
    )
    with op.batch_alter_table("repositories", schema=None) as batch_op:
        batch_op.alter_column(
            "encryption_type", existing_type=sa.String(), nullable=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("repositories", schema=None) as batch_op:
        batch_op.alter_column(
            "encryption_type", existing_type=sa.String(), nullable=True
        )
