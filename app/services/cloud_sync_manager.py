"""
CloudSyncManager - Handles cloud synchronization operations
"""

import logging
from typing import Dict, Optional, Callable

from app.models.database import Repository, CloudSyncConfig
from app.utils.db_session import get_db_session

logger = logging.getLogger(__name__)


class CloudSyncManager:
    """
    Handles cloud synchronization operations.

    Responsibilities:
    - Execute cloud sync tasks
    - Manage cloud provider configurations
    - Handle S3 and other cloud provider integrations
    - Coordinate with rclone service for file transfers
    """

    def __init__(self, db_session_factory: Callable = None):
        self._db_session_factory = db_session_factory or get_db_session

    async def execute_cloud_sync_task(
        self,
        repository_id: int,
        cloud_sync_config_id: Optional[int],
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Execute a cloud sync task for a repository"""
        try:
            # Get repository data
            repo_data = self._get_repository_data(repository_id)
            if not repo_data:
                logger.error(f"Repository {repository_id} not found")
                return False

            # Check for cloud_sync_config_id
            if not cloud_sync_config_id:
                logger.info("📋 No cloud backup configuration - skipping cloud sync")
                if output_callback:
                    output_callback(
                        "📋 No cloud backup configuration - skipping cloud sync"
                    )
                return True  # Not an error, just skipped

            logger.info(f"☁️ Starting cloud sync for repository {repo_data['name']}")
            if output_callback:
                output_callback(
                    f"☁️ Starting cloud sync for repository {repo_data['name']}"
                )

            # Get cloud backup configuration
            with self._db_session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == cloud_sync_config_id)
                    .first()
                )

                if not config or not config.enabled:
                    logger.info(
                        "📋 Cloud backup configuration not found or disabled - skipping"
                    )
                    if output_callback:
                        output_callback(
                            "📋 Cloud backup configuration not found or disabled - skipping"
                        )
                    return True  # Not an error, just skipped

                # Handle different provider types
                return await self._sync_to_provider(config, repo_data, output_callback)

        except Exception as e:
            error_msg = f"Cloud sync failed: {str(e)}"
            logger.error(error_msg)
            if output_callback:
                output_callback(error_msg)
            return False

    async def _sync_to_provider(
        self,
        config: CloudSyncConfig,
        repo_data: Dict,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Sync to the specific cloud provider"""
        try:
            if config.provider == "s3":
                return await self._sync_to_s3(config, repo_data, output_callback)
            else:
                error_msg = f"Unsupported cloud provider: {config.provider}"
                logger.error(error_msg)
                if output_callback:
                    output_callback(error_msg)
                return False
        except Exception as e:
            error_msg = f"Provider sync failed: {str(e)}"
            logger.error(error_msg)
            if output_callback:
                output_callback(error_msg)
            return False

    async def _sync_to_s3(
        self,
        config: CloudSyncConfig,
        repo_data: Dict,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Sync repository to S3 using rclone"""
        try:
            # Get S3 credentials
            access_key, secret_key = config.get_credentials()

            logger.info(f"☁️ Syncing to {config.name} (S3: {config.bucket_name})")
            if output_callback:
                output_callback(
                    f"☁️ Syncing to {config.name} (S3: {config.bucket_name})"
                )

            # Create a simple repository object for rclone service
            from types import SimpleNamespace

            repo_obj = SimpleNamespace()
            repo_obj.name = repo_data["name"]
            repo_obj.path = repo_data["path"]

            # Import and use RcloneService
            from app.services.rclone_service import RcloneService

            rclone_service = RcloneService()

            # Create the S3 configuration
            s3_config = {
                "type": "s3",
                "access_key_id": access_key,
                "secret_access_key": secret_key,
                "region": config.region or "us-east-1",
                "endpoint": config.endpoint,
            }

            # Set up progress callback if provided
            progress_callback = None
            if output_callback:

                def progress_callback(line: str):
                    output_callback(f"☁️ {line}")

            # Start the sync
            result = await rclone_service.sync_to_s3(
                repository=repo_obj,
                bucket_name=config.bucket_name,
                s3_config=s3_config,
                progress_callback=progress_callback,
            )

            if result["success"]:
                success_msg = "✅ Cloud sync completed successfully"
                logger.info(success_msg)
                if output_callback:
                    output_callback(success_msg)
                    if result.get("stats"):
                        stats = result["stats"]
                        output_callback(
                            f"📊 Transferred: {stats.get('bytes', 0)} bytes"
                        )
                        output_callback(f"📊 Files: {stats.get('files', 0)} files")
                return True
            else:
                error_msg = (
                    f"❌ Cloud sync failed: {result.get('error', 'Unknown error')}"
                )
                logger.error(error_msg)
                if output_callback:
                    output_callback(error_msg)
                return False

        except ImportError as e:
            error_msg = f"RcloneService not available: {str(e)}"
            logger.error(error_msg)
            if output_callback:
                output_callback(error_msg)
            return False
        except Exception as e:
            error_msg = f"S3 sync failed: {str(e)}"
            logger.error(error_msg)
            if output_callback:
                output_callback(error_msg)
            return False

    def _get_repository_data(self, repository_id: int) -> Optional[Dict]:
        """Get repository data from database"""
        try:
            with self._db_session_factory() as db:
                repo = (
                    db.query(Repository).filter(Repository.id == repository_id).first()
                )
                if repo:
                    return {"id": repo.id, "name": repo.name, "path": repo.path}
                return None
        except Exception as e:
            logger.error(f"Error getting repository data: {e}")
            return None

    async def validate_cloud_config(self, config_id: int) -> Dict[str, any]:
        """Validate a cloud sync configuration"""
        try:
            with self._db_session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == config_id)
                    .first()
                )

                if not config:
                    return {"valid": False, "error": "Configuration not found"}

                if not config.enabled:
                    return {"valid": False, "error": "Configuration is disabled"}

                # Provider-specific validation
                if config.provider == "s3":
                    return await self._validate_s3_config(config)
                else:
                    return {
                        "valid": False,
                        "error": f"Unsupported provider: {config.provider}",
                    }

        except Exception as e:
            return {"valid": False, "error": f"Validation error: {str(e)}"}

    async def _validate_s3_config(self, config: CloudSyncConfig) -> Dict[str, any]:
        """Validate S3 configuration"""
        try:
            # Check required fields
            if not config.bucket_name:
                return {"valid": False, "error": "S3 bucket name is required"}

            # Try to get credentials
            try:
                access_key, secret_key = config.get_credentials()
                if not access_key or not secret_key:
                    return {"valid": False, "error": "S3 credentials are required"}
            except Exception as e:
                return {"valid": False, "error": f"Invalid S3 credentials: {str(e)}"}

            # Could add more validation like testing connection to S3
            # For now, just check basic configuration
            return {
                "valid": True,
                "provider": "s3",
                "bucket": config.bucket_name,
                "region": config.region or "us-east-1",
            }

        except Exception as e:
            return {"valid": False, "error": f"S3 validation error: {str(e)}"}

    async def get_sync_status(self, config_id: int) -> Dict[str, any]:
        """Get status information for a cloud sync configuration"""
        try:
            with self._db_session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == config_id)
                    .first()
                )

                if not config:
                    return {"exists": False, "error": "Configuration not found"}

                return {
                    "exists": True,
                    "enabled": config.enabled,
                    "provider": config.provider,
                    "name": config.name,
                    "bucket_name": getattr(config, "bucket_name", None),
                    "region": getattr(config, "region", None),
                    "created_at": config.created_at.isoformat()
                    if hasattr(config, "created_at") and config.created_at
                    else None,
                }

        except Exception as e:
            return {"exists": False, "error": f"Status check error: {str(e)}"}
