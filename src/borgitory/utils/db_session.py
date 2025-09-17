"""Database session utilities for proper session lifecycle management."""

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session
from borgitory.models.database import get_db

logger = logging.getLogger(__name__)


@contextmanager
def get_db_session() -> Iterator[Session]:
    """Context manager for database sessions with proper cleanup.

    Usage:
        with get_db_session() as db:
            # database operations
            pass

    Automatically handles:
    - Session creation
    - Commit on success
    - Rollback on exception
    - Session cleanup
    """
    db = next(get_db())
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()
