"""Initial empty state

Revision ID: 9f06f8c8088d
Revises:
Create Date: 2025-09-19 22:46:16.757334

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "9f06f8c8088d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
