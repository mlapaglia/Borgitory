import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from collections import deque

from sqlalchemy.orm import Session
from app.models.database import Repository, Job, JobTask, get_db, Schedule
from app.services.borg_service import borg_service
from app.services.rclone_service import rclone_service

logger = logging.getLogger(__name__)

@dataclass
class CompositeJobTaskInfo:
    task_type: str  # 'backup', 'cloud_sync'
    task_name: str
    status: str = 'pending'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_lines: deque = field(default_factory=lambda: deque(maxlen=1000))
    error: Optional[str] = None
    return_code: Optional[int] = None
    # Backup-specific parameters
    source_path: Optional[str] = None
    compression: Optional[str] = None
    dry_run: Optional[bool] = None

@dataclass
class CompositeJobInfo:
    id: str
    db_job_id: int
    job_type: str  # 'scheduled_backup', 'manual_backup'
    status: str = 'pending'
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tasks: List[CompositeJobTaskInfo] = field(default_factory=list)
    current_task_index: int = 0
    repository: Optional['Repository'] = None
    schedule: Optional['Schedule'] = None

class CompositeJobManager:
    def __init__(self):
        self.jobs: Dict[str, CompositeJobInfo] = {}
        self._event_queues: List[asyncio.Queue] = []  # For SSE streaming
        
    async def create_composite_job(
        self, 
        job_type: str, 
        task_definitions: List[Dict], 
        repository: Repository,
        schedule: Optional[Schedule] = None,
        cloud_backup_config_id: Optional[int] = None
    ) -> str:
        """Create a new composite job with multiple tasks"""
        
        job_id = str(uuid.uuid4())
        
        # Create database job record
        db = next(get_db())
        try:
            db_job = Job(
                repository_id=repository.id,
                job_uuid=job_id,
                type=job_type,
                status="pending",
                job_type="composite",
                total_tasks=len(task_definitions),
                completed_tasks=0,
                cloud_backup_config_id=cloud_backup_config_id,
                started_at=datetime.now()
            )
            db.add(db_job)
            db.commit()
            db.refresh(db_job)
            
            # Create task records
            for i, task_def in enumerate(task_definitions):
                task = JobTask(
                    job_id=db_job.id,
                    task_type=task_def['type'],
                    task_name=task_def['name'],
                    status="pending",
                    task_order=i
                )
                db.add(task)
            
            db.commit()
            
            logger.info(f"📝 Created composite job {job_id} (db_id: {db_job.id}) with {len(task_definitions)} tasks")
            
        except Exception as e:
            logger.error(f"Failed to create database job: {e}")
            raise
        finally:
            db.close()
        
        # Create in-memory job info
        composite_job = CompositeJobInfo(
            id=job_id,
            db_job_id=db_job.id,
            job_type=job_type,
            repository=repository,
            schedule=schedule
        )
        
        # Create task info objects
        for task_def in task_definitions:
            task_info = CompositeJobTaskInfo(
                task_type=task_def['type'],
                task_name=task_def['name'],
                source_path=task_def.get('source_path'),
                compression=task_def.get('compression'),
                dry_run=task_def.get('dry_run')
            )
            composite_job.tasks.append(task_info)
        
        self.jobs[job_id] = composite_job
        
        # Start executing the job
        asyncio.create_task(self._execute_composite_job(job_id))
        
        return job_id
    
    async def _execute_composite_job(self, job_id: str):
        """Execute all tasks in a composite job sequentially"""
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        logger.info(f"🚀 Starting composite job {job_id} ({job.job_type})")
        
        job.status = 'running'
        self._update_job_status(job_id, 'running')
        
        try:
            # Execute each task sequentially
            for i, task in enumerate(job.tasks):
                job.current_task_index = i
                
                logger.info(f"🔄 Starting task {i+1}/{len(job.tasks)}: {task.task_name}")
                
                task.status = 'running'
                task.started_at = datetime.now()
                self._update_task_status(job_id, i, 'running')
                
                try:
                    # Execute the specific task
                    success = await self._execute_task(job, task, i)
                    
                    if success:
                        task.status = 'completed'
                        task.completed_at = datetime.now()
                        task.return_code = 0
                        self._update_task_status(job_id, i, 'completed', return_code=0)
                        
                        # Update completed tasks count
                        job.completed_tasks = i + 1
                        self._update_job_progress(job_id)
                        
                        logger.info(f"✅ Task {i+1}/{len(job.tasks)} completed: {task.task_name}")
                    else:
                        task.status = 'failed'
                        task.completed_at = datetime.now()
                        task.return_code = 1
                        self._update_task_status(job_id, i, 'failed', return_code=1)
                        
                        logger.error(f"❌ Task {i+1}/{len(job.tasks)} failed: {task.task_name}")
                        
                        # Fail the entire job if a task fails
                        job.status = 'failed'
                        job.completed_at = datetime.now()
                        self._update_job_status(job_id, 'failed')
                        return
                        
                except Exception as e:
                    logger.error(f"❌ Exception in task {task.task_name}: {str(e)}")
                    task.status = 'failed'
                    task.completed_at = datetime.now()
                    task.return_code = 1
                    task.error = str(e)
                    self._update_task_status(job_id, i, 'failed', error=str(e), return_code=1)
                    
                    # Fail the entire job
                    job.status = 'failed'
                    job.completed_at = datetime.now()
                    self._update_job_status(job_id, 'failed')
                    return
            
            # All tasks completed successfully
            job.status = 'completed'
            job.completed_at = datetime.now()
            self._update_job_status(job_id, 'completed')
            
            logger.info(f"🎉 Composite job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Fatal error in composite job {job_id}: {str(e)}")
            job.status = 'failed'
            job.completed_at = datetime.now()
            self._update_job_status(job_id, 'failed')
    
    async def _execute_task(self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int) -> bool:
        """Execute a specific task type"""
        
        if task.task_type == 'backup':
            return await self._execute_backup_task(job, task, task_index)
        elif task.task_type == 'cloud_sync':
            return await self._execute_cloud_sync_task(job, task, task_index)
        else:
            logger.error(f"Unknown task type: {task.task_type}")
            return False
    
    async def _execute_backup_task(self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int) -> bool:
        """Execute a borg backup task"""
        try:
            logger.info(f"🔄 Starting borg backup for repository {job.repository.name}")
            
            # DEBUG: Enable test mode for slow fake backup
            TEST_MODE = False  # Set to False for real borg backups
            
            if TEST_MODE:
                return await self._execute_fake_backup_task(job, task, task_index)
            
            # Use the existing borg service to create backup
            # But we'll stream the output to our task instead of creating a separate job
            from app.utils.security import build_secure_borg_command
            from datetime import datetime
            from app.utils.security import validate_compression, validate_archive_name
            
            # Build the backup command
            compression = "zstd"
            archive_name = f"backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            
            validate_compression(compression)
            validate_archive_name(archive_name)
            
            # Get source path from task or default to /data
            source_path = task.source_path or "/data"
            compression_setting = task.compression or "zstd"
            
            logger.info(f"🔄 Backup settings - Source: {source_path}, Compression: {compression_setting}, Dry run: {task.dry_run}")
            
            additional_args = [
                "--compression", compression_setting,
                "--stats",
                "--progress", 
                "--json",
                "--verbose",  # More verbose output
                "--list",     # List files being processed
                f"{job.repository.path}::{archive_name}",
                source_path
            ]
            
            # Add dry run flag if requested
            if task.dry_run:
                additional_args.insert(0, "--dry-run")
            
            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path="",
                passphrase=job.repository.get_passphrase(),
                additional_args=additional_args
            )
            
            # Execute the command and capture output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            
            # Stream output to task
            async for line in process.stdout:
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                task.output_lines.append({
                    'timestamp': datetime.now().isoformat(),
                    'text': decoded_line
                })
                
                # Broadcast output
                self._broadcast_task_output(job.id, task_index, decoded_line)
                
                # DEBUG: Add artificial delay for testing streaming
                await asyncio.sleep(0.5)  # Half second delay per line
            
            await process.wait()
            
            if process.returncode == 0:
                logger.info(f"✅ Backup task completed successfully")
                return True
            else:
                logger.error(f"❌ Backup task failed with return code {process.returncode}")
                task.error = f"Backup failed with return code {process.returncode}"
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception in backup task: {str(e)}")
            task.error = str(e)
            return False
    
    async def _execute_fake_backup_task(self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int) -> bool:
        """Execute a fake slow backup for testing streaming output"""
        try:
            logger.info(f"🧪 Starting FAKE backup for testing (repository: {job.repository.name})")
            
            # Simulate borg backup output with realistic messages
            fake_output_lines = [
                "Repository lock acquired",
                "------------------------------------------------------------------------------",
                "Archive name: backup-2024-01-15_14-30-25", 
                "Archive fingerprint: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
                "Time (start): Mon, 2024-01-15 14:30:25",
                "Time (end):   Mon, 2024-01-15 14:35:42",
                "Duration: 5 minutes 17.23 seconds",
                "Number of files: 1247",
                "Utilization of max. archive size: 0%",
                "------------------------------------------------------------------------------",
                "",
                "Scanning files...",
                "Processing: /data/documents/file1.txt",
                "Processing: /data/documents/file2.pdf", 
                "Processing: /data/images/photo1.jpg",
                "Processing: /data/images/photo2.png",
                "Processing: /data/videos/video1.mp4",
                "Processing: /data/config/settings.json",
                "Processing: /data/logs/application.log",
                "Processing: /data/backups/old_backup.tar.gz",
                "",
                "A /data/documents/file1.txt",
                "A /data/documents/file2.pdf", 
                "A /data/images/photo1.jpg",
                "A /data/images/photo2.png",
                "M /data/videos/video1.mp4",
                "A /data/config/settings.json",
                "M /data/logs/application.log",
                "U /data/backups/old_backup.tar.gz",
                "",
                '{"original_size": 52428800, "compressed_size": 41943040, "deduplicated_size": 20971520}',
                "",
                "------------------------------------------------------------------------------",
                "Original size      Compressed size    Deduplicated size",
                "This archive:        50.00 MB            40.00 MB            20.00 MB", 
                "All archives:       500.00 MB           400.00 MB           200.00 MB",
                "",
                "                       Unique chunks         Total chunks",
                "Chunk index:                    1532                 3847",
                "------------------------------------------------------------------------------",
                "",
                "Archive successfully created"
            ]
            
            # Stream each line with a delay
            for i, line in enumerate(fake_output_lines):
                # Add timestamp and store
                task.output_lines.append({
                    'timestamp': datetime.now().isoformat(),
                    'text': line
                })
                
                # Broadcast output
                self._broadcast_task_output(job.id, task_index, line)
                
                # Variable delay based on content (faster for empty lines, slower for file processing)
                if line.startswith("Processing:") or line.startswith("A ") or line.startswith("M "):
                    await asyncio.sleep(0.8)  # Slow for file operations
                elif line.strip() == "":
                    await asyncio.sleep(0.2)  # Fast for empty lines
                elif "scanning" in line.lower() or "repository" in line.lower():
                    await asyncio.sleep(1.5)  # Very slow for major operations
                else:
                    await asyncio.sleep(0.4)  # Medium for other lines
                
                logger.info(f"🧪 Fake backup output [{i+1}/{len(fake_output_lines)}]: {line}")
            
            logger.info(f"✅ Fake backup task completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Exception in fake backup task: {str(e)}")
            task.error = str(e)
            return False
    
    async def _execute_cloud_sync_task(self, job: CompositeJobInfo, task: CompositeJobTaskInfo, task_index: int) -> bool:
        """Execute a cloud sync task"""
        try:
            if not job.schedule or not job.schedule.cloud_backup_config_id:
                logger.info("📋 No cloud backup configuration - skipping cloud sync")
                task.status = 'skipped'
                return True
            
            logger.info(f"☁️ Starting cloud sync for repository {job.repository.name}")
            
            # Get cloud backup configuration
            db = next(get_db())
            try:
                from app.models.database import CloudBackupConfig
                config = db.query(CloudBackupConfig).filter(
                    CloudBackupConfig.id == job.schedule.cloud_backup_config_id
                ).first()
                
                if not config or not config.enabled:
                    logger.info("📋 Cloud backup configuration not found or disabled - skipping")
                    task.status = 'skipped'
                    return True
                
                # Handle different provider types
                if config.provider == "s3":
                    # Get S3 credentials
                    access_key, secret_key = config.get_credentials()
                    
                    logger.info(f"☁️ Syncing to {config.name} (S3: {config.bucket_name})")
                    
                    # Use rclone service to sync to S3
                    progress_generator = rclone_service.sync_repository_to_s3(
                        repository=job.repository,
                        access_key_id=access_key,
                        secret_access_key=secret_key,
                        bucket_name=config.bucket_name,
                        region=config.region,
                        path_prefix=config.path_prefix or "",
                        endpoint=config.endpoint
                    )
                    
                elif config.provider == "sftp":
                    # Get SFTP credentials
                    password, private_key = config.get_sftp_credentials()
                    
                    logger.info(f"☁️ Syncing to {config.name} (SFTP: {config.host}:{config.remote_path})")
                    
                    # Use rclone service to sync to SFTP
                    progress_generator = rclone_service.sync_repository_to_sftp(
                        repository=job.repository,
                        host=config.host,
                        username=config.username,
                        remote_path=config.remote_path,
                        port=config.port or 22,
                        password=password if password else None,
                        private_key=private_key if private_key else None,
                        path_prefix=config.path_prefix or ""
                    )
                    
                else:
                    logger.error(f"❌ Unsupported cloud backup provider: {config.provider}")
                    task.error = f"Unsupported provider: {config.provider}"
                    return False
                
                # Process progress from either S3 or SFTP sync
                async for progress in progress_generator:
                    if progress.get("type") == "log":
                        log_line = f"[{progress['stream']}] {progress['message']}"
                        task.output_lines.append({
                            'timestamp': datetime.now().isoformat(),
                            'text': log_line
                        })
                        self._broadcast_task_output(job.id, task_index, log_line)
                        
                    elif progress.get("type") == "error":
                        task.error = progress["message"]
                        logger.error(f"❌ Cloud sync error: {progress['message']}")
                        return False
                        
                    elif progress.get("type") == "completed":
                        if progress["status"] == "success":
                            logger.info(f"✅ Cloud sync completed successfully")
                            return True
                        else:
                            logger.error(f"❌ Cloud sync failed")
                            return False
                
                # If we get here, sync completed without explicit success/failure
                logger.info(f"✅ Cloud sync completed")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Exception in cloud sync task: {str(e)}")
            task.error = str(e)
            return False
    
    def _update_job_status(self, job_id: str, status: str):
        """Update job status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return
                
            db = next(get_db())
            try:
                db_job = db.query(Job).filter(Job.id == job.db_job_id).first()
                if db_job:
                    db_job.status = status
                    if status == 'completed' or status == 'failed':
                        db_job.finished_at = datetime.now()
                    db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
    
    def _update_job_progress(self, job_id: str):
        """Update job progress in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return
                
            db = next(get_db())
            try:
                db_job = db.query(Job).filter(Job.id == job.db_job_id).first()
                if db_job:
                    db_job.completed_tasks = job.completed_tasks
                    db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to update job progress: {e}")
    
    def _update_task_status(self, job_id: str, task_index: int, status: str, error: str = None, return_code: int = None):
        """Update task status in database"""
        try:
            job = self.jobs.get(job_id)
            if not job:
                return
                
            db = next(get_db())
            try:
                task = db.query(JobTask).filter(
                    JobTask.job_id == job.db_job_id,
                    JobTask.task_order == task_index
                ).first()
                
                if task:
                    task.status = status
                    if status == 'running':
                        task.started_at = datetime.now()
                    elif status in ['completed', 'failed', 'skipped']:
                        task.completed_at = datetime.now()
                        
                        # Store output from in-memory task
                        if task_index < len(job.tasks):
                            task_info = job.tasks[task_index]
                            if task_info.output_lines:
                                task.output = '\n'.join([line['text'] for line in task_info.output_lines])
                        
                    if error:
                        task.error = error
                    if return_code is not None:
                        task.return_code = return_code
                        
                    db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
    
    def _broadcast_task_output(self, job_id: str, task_index: int, line: str):
        """Broadcast task output to SSE listeners"""
        event_data = {
            "type": "task_output",
            "job_id": job_id,
            "task_index": task_index,
            "line": line,
            "timestamp": datetime.now().isoformat()
        }
        
        for queue in self._event_queues:
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                pass  # Skip if queue is full
    
    def subscribe_to_events(self) -> asyncio.Queue:
        """Subscribe to job events for SSE streaming"""
        queue = asyncio.Queue(maxsize=100)
        self._event_queues.append(queue)
        return queue
    
    def unsubscribe_from_events(self, queue: asyncio.Queue):
        """Unsubscribe from job events"""
        if queue in self._event_queues:
            self._event_queues.remove(queue)

# Global composite job manager instance
composite_job_manager = CompositeJobManager()