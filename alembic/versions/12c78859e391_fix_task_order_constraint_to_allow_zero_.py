"""Fix task_order constraint to allow zero-based indexing

Revision ID: 12c78859e391
Revises: eff6fe73191d
Create Date: 2025-09-05 15:35:39.780608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12c78859e391'
down_revision: Union[str, Sequence[str], None] = 'eff6fe73191d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix task_order constraint to allow zero-based indexing."""
    with op.batch_alter_table('job_tasks') as batch_op:
        batch_op.drop_constraint('ck_job_tasks_order_positive', type_='check')
        batch_op.create_check_constraint(
            'ck_job_tasks_order_non_negative',
            sa.text("task_order >= 0")
        )


def downgrade() -> None:
    """Revert to positive-only task_order constraint."""
    with op.batch_alter_table('job_tasks') as batch_op:
        batch_op.drop_constraint('ck_job_tasks_order_non_negative', type_='check')
        batch_op.create_check_constraint(
            'ck_job_tasks_order_positive',
            sa.text("task_order > 0")
        )
