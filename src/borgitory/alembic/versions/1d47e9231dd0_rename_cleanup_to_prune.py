"""rename_cleanup_to_prune

Revision ID: 1d47e9231dd0
Revises: 5e6cc17d11a5
Create Date: 2025-09-25 16:40:52.197284

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1d47e9231dd0"
down_revision: Union[str, Sequence[str], None] = "5e6cc17d11a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename the table from cleanup_configs to prune_configs
    op.rename_table("cleanup_configs", "prune_configs")

    # Rename the indexes to match the new table name
    with op.batch_alter_table("prune_configs", schema=None) as batch_op:
        batch_op.drop_index("ix_cleanup_configs_id")
        batch_op.drop_index("ix_cleanup_configs_name")
        batch_op.create_index("ix_prune_configs_id", ["id"])
        batch_op.create_index("ix_prune_configs_name", ["name"])

    # Rename the column in jobs table from cleanup_config_id to prune_config_id
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column("cleanup_config_id", new_column_name="prune_config_id")

    # Rename the column in schedules table from cleanup_config_id to prune_config_id
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column("cleanup_config_id", new_column_name="prune_config_id")


def downgrade() -> None:
    """Downgrade schema."""
    # Rename the column in jobs table back from prune_config_id to cleanup_config_id
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column("prune_config_id", new_column_name="cleanup_config_id")

    # Rename the column in schedules table from prune_config_id to cleanup_config_id
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.alter_column("prune_config_id", new_column_name="cleanup_config_id")

    # Rename the indexes back to the original names
    with op.batch_alter_table("prune_configs", schema=None) as batch_op:
        batch_op.drop_index("ix_prune_configs_id")
        batch_op.drop_index("ix_prune_configs_name")
        batch_op.create_index("ix_cleanup_configs_id", ["id"])
        batch_op.create_index("ix_cleanup_configs_name", ["name"])

    # Rename the table back from prune_configs to cleanup_configs
    op.rename_table("prune_configs", "cleanup_configs")
