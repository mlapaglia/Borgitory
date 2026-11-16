"""Store session tokens as SHA-256 hashes

Existing plaintext tokens are hashed in place, so users stay logged in.

Revision ID: a7e2c4f1d8b3
Revises: a4c2e8f1b7d3
Create Date: 2026-11-16 12:00:00.000000

"""

import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7e2c4f1d8b3"
down_revision: Union[str, Sequence[str], None] = "a4c2e8f1b7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_sessions = sa.table(
    "user_sessions",
    sa.column("id", sa.Integer),
    sa.column("session_token", sa.String),
)


def upgrade() -> None:
    """Hash every stored session token (kept self-contained: no app imports)."""
    bind = op.get_bind()
    rows = bind.execute(sa.select(user_sessions.c.id, user_sessions.c.session_token))
    for row_id, token in rows.fetchall():
        hashed = hashlib.sha256(token.encode("utf-8")).hexdigest()
        bind.execute(
            user_sessions.update()
            .where(user_sessions.c.id == row_id)
            .values(session_token=hashed)
        )


def downgrade() -> None:
    """Hashes cannot be reversed; drop all sessions so users log in again."""
    op.execute(user_sessions.delete())
