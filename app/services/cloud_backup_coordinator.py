"""
Cloud Backup Coordinator - Coordinates post-backup cloud sync operations
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, UTC
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CloudBackupStatus(Enum):
    """Status of cloud backup operations"""
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CloudBackupTask:
    """Represents a cloud backup task"""
    task_id: str
    repository_id: int
    cloud_sync_config_id: int
    source_job_id: Optional[int] = None
    status: CloudBackupStatus = CloudBackupStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.progress is None:
            self.progress = {}


class CloudBackupCoordinator:
    """Coordinates post-backup cloud sync operations"""
    
    def __init__(
        self,
        db_session_factory: Optional[Callable] = None,
        rclone_service: Optional[Any] = None,
        http_client_factory: Optional[Callable] = None
    ):
        self.db_session_factory = db_session_factory or self._default_db_session_factory
        self.rclone_service = rclone_service
        self.http_client_factory = http_client_factory
        
        # Active cloud backup tasks
        self._active_tasks: Dict[str, CloudBackupTask] = {}
        self._task_futures: Dict[str, asyncio.Task] = {}
        
        # Configuration
        self.max_concurrent_uploads = 3
        self._upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        self._shutdown_requested = False
    
    def _default_db_session_factory(self):
        """Default database session factory"""
        from app.utils.db_session import get_db_session
        return get_db_session()
    
    async def trigger_cloud_backup(
        self,
        repository_data: Dict[str, Any],
        cloud_sync_config_id: int,
        source_job_id: Optional[int] = None
    ) -> Optional[str]:
        """Trigger a cloud backup operation"""
        
        # Check if cloud backup should be triggered
        if not await self._should_trigger_cloud_backup(
            repository_data["id"], cloud_sync_config_id
        ):
            logger.info(
                f"Cloud backup not triggered for repository {repository_data['id']} "
                f"(config {cloud_sync_config_id})"
            )
            return None
        
        task_id = f"cloud_backup_{repository_data['id']}_{cloud_sync_config_id}_{datetime.now().timestamp()}"
        
        task = CloudBackupTask(
            task_id=task_id,
            repository_id=repository_data["id"],
            cloud_sync_config_id=cloud_sync_config_id,
            source_job_id=source_job_id,
            started_at=datetime.now(UTC)
        )
        
        self._active_tasks[task_id] = task
        
        # Start cloud backup task
        future = asyncio.create_task(
            self._execute_cloud_backup(task, repository_data)
        )
        self._task_futures[task_id] = future
        
        logger.info(
            f"Started cloud backup task {task_id} for repository {repository_data['name']}"
        )
        
        return task_id
    
    async def _should_trigger_cloud_backup(
        self,
        repository_id: int,
        cloud_sync_config_id: int
    ) -> bool:
        """Check if cloud backup should be triggered"""
        try:
            from app.models.database import CloudSyncConfig
            
            with self.db_session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == cloud_sync_config_id)
                    .first()
                )
                
                if not config:
                    logger.warning(f"Cloud sync config {cloud_sync_config_id} not found")
                    return False
                
                if not config.enabled:
                    logger.info(f"Cloud sync config {cloud_sync_config_id} is disabled")
                    return False
                
                # Check if backup service is available
                if not self.rclone_service:
                    logger.warning("No rclone service configured for cloud backup")
                    return False
                
                logger.info(
                    f"Cloud backup approved for repository {repository_id} "
                    f"using config {cloud_sync_config_id}"
                )
                return True
                
        except Exception as e:
            logger.error(f"Error checking cloud backup eligibility: {e}")
            return False
    
    async def _execute_cloud_backup(
        self,
        task: CloudBackupTask,
        repository_data: Dict[str, Any]
    ) -> None:
        """Execute the cloud backup process"""
        async with self._upload_semaphore:
            try:
                task.status = CloudBackupStatus.STARTING
                logger.info(f"Starting cloud backup execution for task {task.task_id}")
                
                # Get cloud sync configuration
                cloud_config = await self._get_cloud_sync_config(task.cloud_sync_config_id)
                if not cloud_config:
                    raise Exception("Cloud sync configuration not found")
                
                task.status = CloudBackupStatus.RUNNING
                
                # Execute cloud backup using rclone service
                if self.rclone_service:
                    await self._execute_rclone_backup(task, repository_data, cloud_config)
                else:
                    raise Exception("No cloud backup service available")
                
                # Mark as completed
                task.status = CloudBackupStatus.COMPLETED
                task.completed_at = datetime.now(UTC)
                
                logger.info(f"Cloud backup task {task.task_id} completed successfully")
                
                # Update database with completion
                await self._update_cloud_backup_status(task)
                
            except Exception as e:
                task.status = CloudBackupStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.now(UTC)
                
                logger.error(f"Cloud backup task {task.task_id} failed: {e}")
                
                # Update database with failure
                await self._update_cloud_backup_status(task)
                
            finally:
                # Clean up
                if task.task_id in self._task_futures:
                    del self._task_futures[task.task_id]
    
    async def _execute_rclone_backup(
        self,
        task: CloudBackupTask,
        repository_data: Dict[str, Any],
        cloud_config: Dict[str, Any]
    ) -> None:
        """Execute backup using rclone service"""
        try:
            # Prepare rclone parameters
            source_path = repository_data["path"]
            remote_path = f"{cloud_config['remote_name']}:{cloud_config['remote_path']}"
            
            # Progress callback to update task status
            def progress_callback(progress_info: Dict[str, Any]):
                task.progress.update(progress_info)
            
            # Use rclone service to perform the backup
            result = await self.rclone_service.sync_repository(
                source_path=source_path,
                remote_path=remote_path,
                config=cloud_config,
                progress_callback=progress_callback
            )
            
            if not result["success"]:
                raise Exception(f"Rclone backup failed: {result.get('error', 'Unknown error')}")
            
            # Update task with final progress
            task.progress.update(result.get("stats", {}))
            
        except Exception as e:
            logger.error(f"Rclone backup failed for task {task.task_id}: {e}")
            raise
    
    async def _get_cloud_sync_config(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Get cloud sync configuration"""
        try:
            from app.models.database import CloudSyncConfig
            
            with self.db_session_factory() as db:
                config = (
                    db.query(CloudSyncConfig)
                    .filter(CloudSyncConfig.id == config_id)
                    .first()
                )
                
                if not config:
                    return None
                
                return {
                    "id": config.id,
                    "name": config.name,
                    "remote_name": config.remote_name,
                    "remote_path": config.remote_path,
                    "enabled": config.enabled,
                    "sync_options": config.sync_options or {}
                }
                
        except Exception as e:
            logger.error(f"Failed to get cloud sync config {config_id}: {e}")
            return None
    
    async def _update_cloud_backup_status(self, task: CloudBackupTask) -> None:
        """Update database with cloud backup status"""
        try:
            # Create or update cloud backup record
            from app.models.database import CloudBackupJob
            
            with self.db_session_factory() as db:
                # Try to find existing record
                cloud_job = (
                    db.query(CloudBackupJob)
                    .filter(CloudBackupJob.task_id == task.task_id)
                    .first()
                )
                
                if not cloud_job:
                    # Create new record
                    cloud_job = CloudBackupJob(
                        task_id=task.task_id,
                        repository_id=task.repository_id,
                        cloud_sync_config_id=task.cloud_sync_config_id,
                        source_job_id=task.source_job_id,
                        status=task.status.value,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                        error_message=task.error_message,
                        progress_data=task.progress
                    )
                    db.add(cloud_job)
                else:
                    # Update existing record
                    cloud_job.status = task.status.value
                    cloud_job.completed_at = task.completed_at
                    cloud_job.error_message = task.error_message
                    cloud_job.progress_data = task.progress
                
                db.commit()
                
        except Exception as e:
            logger.error(f"Failed to update cloud backup status: {e}")
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get list of active cloud backup tasks"""
        return [
            {
                "task_id": task.task_id,
                "repository_id": task.repository_id,
                "cloud_sync_config_id": task.cloud_sync_config_id,
                "status": task.status.value,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "progress": task.progress
            }
            for task in self._active_tasks.values()
        ]
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        task = self._active_tasks.get(task_id)
        if not task:
            return None
        
        return {
            "task_id": task.task_id,
            "repository_id": task.repository_id,
            "cloud_sync_config_id": task.cloud_sync_config_id,
            "status": task.status.value,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "progress": task.progress
        }
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a cloud backup task"""
        if task_id not in self._active_tasks:
            return False
        
        task = self._active_tasks[task_id]
        future = self._task_futures.get(task_id)
        
        if future and not future.done():
            future.cancel()
            
        task.status = CloudBackupStatus.CANCELLED
        task.completed_at = datetime.now(UTC)
        
        await self._update_cloud_backup_status(task)
        
        logger.info(f"Cancelled cloud backup task {task_id}")
        return True
    
    async def cleanup_completed_tasks(self, max_age_hours: int = 24) -> int:
        """Clean up old completed tasks"""
        current_time = datetime.now(UTC)
        cleaned_count = 0
        
        task_ids_to_remove = []
        
        for task_id, task in self._active_tasks.items():
            if task.status in [CloudBackupStatus.COMPLETED, CloudBackupStatus.FAILED, CloudBackupStatus.CANCELLED]:
                if task.completed_at:
                    age_hours = (current_time - task.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        task_ids_to_remove.append(task_id)
        
        for task_id in task_ids_to_remove:
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            if task_id in self._task_futures:
                del self._task_futures[task_id]
            cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} completed cloud backup tasks")
        
        return cleaned_count
    
    async def shutdown(self):
        """Shutdown cloud backup coordinator"""
        logger.info("Shutting down cloud backup coordinator")
        self._shutdown_requested = True
        
        # Cancel all active tasks
        for task_id, future in list(self._task_futures.items()):
            if not future.done():
                future.cancel()
                try:
                    await future
                except asyncio.CancelledError:
                    pass
        
        # Clear all data
        self._active_tasks.clear()
        self._task_futures.clear()
        
        logger.info("Cloud backup coordinator shutdown complete")