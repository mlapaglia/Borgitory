"""
Data migration script to move existing cloud sync configurations to the new JSON format.

This script migrates existing S3 and SFTP configurations from the old column-based
format to the new provider_config JSON format.
"""

import json
import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from models.database import CloudSyncConfig
from config import DATABASE_URL
from models.database import get_cipher_suite

logger = logging.getLogger(__name__)


def migrate_existing_configs():
    """
    Migrate existing cloud sync configurations to the new JSON format.
    
    This function:
    1. Reads existing S3 and SFTP configurations from the old columns
    2. Converts them to the new JSON format in provider_config
    3. Preserves encrypted sensitive data
    """
    # Create database connection
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        # Get all existing cloud sync configs
        configs = db.query(CloudSyncConfig).all()
        
        migrated_count = 0
        skipped_count = 0
        
        for config in configs:
            # Skip if already migrated (has provider_config)
            if config.provider_config:
                logger.info(f"Skipping config {config.id} - already has provider_config")
                skipped_count += 1
                continue
            
            provider_config = {}
            
            if config.provider == "s3":
                # Migrate S3 configuration
                provider_config = {
                    "bucket_name": config.bucket_name,
                    "region": "us-east-1",  # Default region
                    "storage_class": "STANDARD"  # Default storage class
                }
                
                # Handle encrypted credentials
                if config.encrypted_access_key:
                    provider_config["encrypted_access_key"] = config.encrypted_access_key
                if config.encrypted_secret_key:
                    provider_config["encrypted_secret_key"] = config.encrypted_secret_key
                
                logger.info(f"Migrating S3 config {config.id} for bucket {config.bucket_name}")
                
            elif config.provider == "sftp":
                # Migrate SFTP configuration
                provider_config = {
                    "host": config.host,
                    "port": config.port or 22,
                    "username": config.username,
                    "remote_path": config.remote_path,
                    "host_key_checking": True  # Default to secure
                }
                
                # Handle encrypted credentials
                if config.encrypted_password:
                    provider_config["encrypted_password"] = config.encrypted_password
                if config.encrypted_private_key:
                    provider_config["encrypted_private_key"] = config.encrypted_private_key
                
                logger.info(f"Migrating SFTP config {config.id} for {config.host}")
                
            else:
                logger.warning(f"Unknown provider {config.provider} for config {config.id}")
                skipped_count += 1
                continue
            
            # Save the JSON configuration
            config.provider_config = json.dumps(provider_config)
            migrated_count += 1
        
        # Commit all changes
        db.commit()
        
        logger.info(f"Migration completed: {migrated_count} configs migrated, {skipped_count} skipped")
        print(f"✓ Migration completed: {migrated_count} configs migrated, {skipped_count} skipped")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        db.rollback()
        print(f"✗ Migration failed: {str(e)}")
        return False
        
    finally:
        db.close()


def verify_migration():
    """
    Verify that the migration was successful by checking that all configs
    have valid provider_config JSON.
    """
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        configs = db.query(CloudSyncConfig).all()
        
        valid_count = 0
        invalid_count = 0
        
        for config in configs:
            if not config.provider_config:
                logger.warning(f"Config {config.id} has no provider_config")
                invalid_count += 1
                continue
            
            try:
                # Try to parse the JSON
                provider_config = json.loads(config.provider_config)
                
                # Basic validation based on provider type
                if config.provider == "s3":
                    required_fields = ["bucket_name"]
                elif config.provider == "sftp":
                    required_fields = ["host", "username", "remote_path"]
                else:
                    logger.warning(f"Unknown provider {config.provider}")
                    invalid_count += 1
                    continue
                
                # Check required fields exist
                missing_fields = [field for field in required_fields if field not in provider_config]
                if missing_fields:
                    logger.warning(f"Config {config.id} missing fields: {missing_fields}")
                    invalid_count += 1
                else:
                    valid_count += 1
                    
            except json.JSONDecodeError as e:
                logger.error(f"Config {config.id} has invalid JSON: {str(e)}")
                invalid_count += 1
        
        logger.info(f"Verification completed: {valid_count} valid, {invalid_count} invalid")
        print(f"✓ Verification completed: {valid_count} valid, {invalid_count} invalid")
        
        return invalid_count == 0
        
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Starting cloud config migration...")
    
    # Run migration
    if migrate_existing_configs():
        print("Migration successful, running verification...")
        if verify_migration():
            print("✓ All configurations migrated successfully!")
        else:
            print("✗ Some configurations have issues, please check logs")
    else:
        print("✗ Migration failed, please check logs")
