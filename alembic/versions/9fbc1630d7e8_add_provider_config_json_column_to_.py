"""Add provider_config JSON column to cloud_sync_configs

Revision ID: 9fbc1630d7e8
Revises: 
Create Date: 2025-09-15 16:03:54.564494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fbc1630d7e8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add provider_config JSON column to cloud_sync_configs table."""
    # Add the new provider_config column
    op.add_column('cloud_sync_configs', sa.Column('provider_config', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove provider_config column from cloud_sync_configs table."""
    # Remove the provider_config column
    op.drop_column('cloud_sync_configs', 'provider_config')
