"""Add frequency_days to repository_check_configs

Lets a check policy run at most every N days, so a daily backup schedule can
carry a check that only runs every couple of weeks.

Revision ID: e5b8d2a7c4f9
Revises: b91d3e6a2f57
Create Date: 2026-11-17 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b8d2a7c4f9"
down_revision: Union[str, Sequence[str], None] = "b91d3e6a2f57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("repository_check_configs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("frequency_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("repository_check_configs", schema=None) as batch_op:
        batch_op.drop_column("frequency_days")
