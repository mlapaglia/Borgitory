"""
Migration script to add source_path column to schedules table.
This should be run once when upgrading to support configurable source paths in schedules.
"""

import logging
from sqlalchemy import text
from app.models.database import engine

logger = logging.getLogger(__name__)

def migrate_add_source_path():
    """Add source_path column to schedules table if it doesn't exist"""
    try:
        with engine.connect() as conn:
            # Check if column already exists
            try:
                result = conn.execute(text("SELECT source_path FROM schedules LIMIT 1"))
                logger.info("✅ source_path column already exists in schedules table")
                return
            except Exception:
                # Column doesn't exist, we need to add it
                logger.info("📝 Adding source_path column to schedules table...")
                
                # Add the column with default value
                conn.execute(text("ALTER TABLE schedules ADD COLUMN source_path TEXT NOT NULL DEFAULT '/data'"))
                conn.commit()
                
                logger.info("✅ Successfully added source_path column to schedules table")
                
    except Exception as e:
        logger.error(f"❌ Error during source_path migration: {e}")
        raise

if __name__ == "__main__":
    migrate_add_source_path()