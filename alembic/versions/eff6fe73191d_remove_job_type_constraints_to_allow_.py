"""Remove job type constraints to allow enum values

Revision ID: eff6fe73191d
Revises: 3e16f40409fc
Create Date: 2025-09-05 15:28:50.506662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eff6fe73191d'
down_revision: Union[str, Sequence[str], None] = '3e16f40409fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove job type constraints to allow enum values."""
    # Remove the job type constraints that limit values to specific strings
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.drop_constraint('ck_jobs_type_valid', type_='check')
        batch_op.drop_constraint('ck_jobs_job_type_valid', type_='check')


def downgrade() -> None:
    """Re-add job type constraints."""
    # Re-add the constraints if needed to downgrade
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.create_check_constraint(
            'ck_jobs_type_valid', 
            sa.text("type IN ('backup', 'restore', 'list', 'check', 'prune', 'sync', 'composite')")
        )
        batch_op.create_check_constraint(
            'ck_jobs_job_type_valid',
            sa.text("job_type IN ('simple', 'composite')")
        )
