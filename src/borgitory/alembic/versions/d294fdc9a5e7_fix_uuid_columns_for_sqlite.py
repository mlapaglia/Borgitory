"""fix_uuid_columns_for_sqlite

Revision ID: d294fdc9a5e7
Revises: 18b9095bc772
Create Date: 2025-10-06 11:45:26.561949

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d294fdc9a5e7"
down_revision: Union[str, Sequence[str], None] = "18b9095bc772"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Disable foreign key constraints temporarily
    op.execute("PRAGMA foreign_keys=OFF")

    # Remove dashes from UUIDs in jobs table
    op.execute("UPDATE jobs SET id = REPLACE(id, '-', '')")

    # Remove dashes from UUIDs in job_tasks table
    op.execute("UPDATE job_tasks SET job_id = REPLACE(job_id, '-', '')")

    # Re-enable foreign key constraints
    op.execute("PRAGMA foreign_keys=ON")

    # Update the column types to use Uuid with native_uuid=False
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.VARCHAR(),
            type_=sa.Uuid(native_uuid=False),
            existing_nullable=False,
        )

    with op.batch_alter_table("job_tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "job_id",
            existing_type=sa.VARCHAR(),
            type_=sa.Uuid(native_uuid=False),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Revert column types back to VARCHAR
    with op.batch_alter_table("job_tasks", schema=None) as batch_op:
        batch_op.alter_column(
            "job_id",
            existing_type=sa.Uuid(native_uuid=False),
            type_=sa.VARCHAR(),
            existing_nullable=False,
        )

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.Uuid(native_uuid=False),
            type_=sa.VARCHAR(),
            existing_nullable=False,
        )

    # Disable foreign key constraints temporarily
    op.execute("PRAGMA foreign_keys=OFF")

    # Add dashes back to UUIDs in jobs table
    op.execute(
        "UPDATE jobs SET id = SUBSTR(id, 1, 8) || '-' || SUBSTR(id, 9, 4) || '-' || SUBSTR(id, 13, 4) || '-' || SUBSTR(id, 17, 4) || '-' || SUBSTR(id, 21)"
    )

    # Add dashes back to UUIDs in job_tasks table
    op.execute(
        "UPDATE job_tasks SET job_id = SUBSTR(job_id, 1, 8) || '-' || SUBSTR(job_id, 9, 4) || '-' || SUBSTR(job_id, 13, 4) || '-' || SUBSTR(job_id, 17, 4) || '-' || SUBSTR(job_id, 21)"
    )

    # Re-enable foreign key constraints
    op.execute("PRAGMA foreign_keys=ON")
