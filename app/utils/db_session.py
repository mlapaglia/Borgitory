"""Database session utilities for proper session lifecycle management."""

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session
from app.models.database import get_db

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


@contextmanager
def get_db_session_no_commit() -> Iterator[Session]:
    """Context manager for read-only database sessions.

    Usage:
        with get_db_session_no_commit() as db:
            # read-only operations
            pass

    Does not auto-commit, only handles cleanup.
    """
    db = next(get_db())
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def db_transaction(func):
    """Decorator for functions that need database transactions.

    Usage:
        @db_transaction
        def my_function():
            # Function will receive 'db' as first argument
            pass
    """

    def wrapper(*args, **kwargs):
        with get_db_session() as db:
            return func(db, *args, **kwargs)

    return wrapper


def db_readonly(func):
    """Decorator for read-only database functions.

    Usage:
        @db_readonly
        def my_read_function():
            # Function will receive 'db' as first argument
            pass
    """

    def wrapper(*args, **kwargs):
        with get_db_session_no_commit() as db:
            return func(db, *args, **kwargs)

    return wrapper
