"""Initial empty state

Revision ID: 9f06f8c8088d
Revises:
Create Date: 2025-09-19 22:46:16.757334

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f06f8c8088d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # add this manually once so alembic ignores the tables automatically created by apscheduler
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.VARCHAR(191), primary_key=True),
        sa.Column("next_run_time", sa.Float(), index=True),
        sa.Column("job_state", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("apscheduler_jobs")
