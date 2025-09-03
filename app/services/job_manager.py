import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)

@dataclass
class BorgJob:
    id: str
    command: List[str]
    status: str  # 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: Optional[datetime] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    
    # Streaming output storage
    output_lines: deque = field(default_factory=lambda: deque(maxlen=1000))  # Keep last 1000 lines
    current_progress: Dict = field(default_factory=dict)  # Parsed progress info
    
class BorgJobManager:
    def __init__(self):
        self.jobs: Dict[str, BorgJob] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._event_queues: List[asyncio.Queue] = []  # For SSE streaming
        
        # Job queue system
        self.MAX_CONCURRENT_BACKUPS = 5
        self._backup_queue: asyncio.Queue = asyncio.Queue()
        self._backup_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_BACKUPS)
        self._queue_processor_started = False
        
    async def start_borg_command(
        self, 
        command: List[str],
        env: Optional[Dict] = None,
        is_backup: bool = False
    ) -> str:
        """Start a Borg command and track its output"""
        job_id = str(uuid.uuid4())
        
        job = BorgJob(
            id=job_id,
            command=command,
            status='queued' if is_backup else 'running',
            started_at=datetime.now()
        )
        self.jobs[job_id] = job
        
        if is_backup:
            # Start queue processor if not already running
            if not self._queue_processor_started:
                asyncio.create_task(self._process_backup_queue())
                self._queue_processor_started = True
            
            logger.info(f"Queuing backup job {job_id} with command: {' '.join(command)}")
            
            # Broadcast job queued event
            self._broadcast_job_event({
                "type": "job_queued",
                "job_id": job_id,
                "command": " ".join(command[:3]) + "..." if len(command) > 3 else " ".join(command),
                "status": "queued",
                "started_at": job.started_at.isoformat()
            })
            
            # Add to backup queue
            await self._backup_queue.put((job_id, command, env))
            
        else:
            # Non-backup jobs run immediately
            logger.info(f"Starting Borg job {job_id} with command: {' '.join(command)}")
            
            # Broadcast job started event
            self._broadcast_job_event({
                "type": "job_started",
                "job_id": job_id,
                "command": " ".join(command[:3]) + "..." if len(command) > 3 else " ".join(command),
                "status": "running",
                "started_at": job.started_at.isoformat()
            })
            
            # Start the subprocess with output streaming
            asyncio.create_task(self._run_borg_job(job_id, command, env))
        
        return job_id
    
    async def _process_backup_queue(self):
        """Process the backup queue, respecting concurrent limits"""
        logger.info(f"Started backup queue processor (max concurrent: {self.MAX_CONCURRENT_BACKUPS})")
        
        while True:
            try:
                # Get next job from queue (this blocks until a job is available)
                job_id, command, env = await self._backup_queue.get()
                
                # Acquire semaphore (this blocks if we've reached the concurrent limit)
                await self._backup_semaphore.acquire()
                
                # Update job status to running and broadcast event
                if job_id in self.jobs:
                    job = self.jobs[job_id]
                    job.status = 'running'
                    
                    logger.info(f"Starting queued backup job {job_id} ({self.MAX_CONCURRENT_BACKUPS - self._backup_semaphore._value}/{self.MAX_CONCURRENT_BACKUPS} slots used)")
                    
                    self._broadcast_job_event({
                        "type": "job_started",
                        "job_id": job_id,
                        "command": " ".join(command[:3]) + "..." if len(command) > 3 else " ".join(command),
                        "status": "running",
                        "started_at": job.started_at.isoformat()
                    })
                    
                    # Start the backup job and release semaphore when done
                    asyncio.create_task(self._run_backup_with_semaphore(job_id, command, env))
                
                # Mark this queue item as done
                self._backup_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in backup queue processor: {e}")
                await asyncio.sleep(1)  # Prevent tight error loops
    
    async def _run_backup_with_semaphore(self, job_id: str, command: List[str], env: Optional[Dict]):
        """Run a backup job and release the semaphore when complete"""
        try:
            await self._run_borg_job(job_id, command, env)
        finally:
            # Always release the semaphore to allow next queued job
            self._backup_semaphore.release()
            logger.info(f"Released backup slot for job {job_id} ({self.MAX_CONCURRENT_BACKUPS - self._backup_semaphore._value}/{self.MAX_CONCURRENT_BACKUPS} slots used)")
    
    async def _run_borg_job(self, job_id: str, command: List[str], env: Optional[Dict]):
        job = self.jobs[job_id]
        
        try:
            # Create subprocess with line-buffered output
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Combine stderr with stdout
                env=env
            )
            
            self._processes[job_id] = process
            
            logger.info(f"Borg job {job_id} started with PID {process.pid}")
            
            # Stream output line by line
            async for line in process.stdout:
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                
                # Store the line
                job.output_lines.append({
                    'timestamp': datetime.now().isoformat(),
                    'text': decoded_line
                })
                
                # Log the output to console for debugging
                logger.info(f"Borg job {job_id} output: {decoded_line}")
                
                # Parse Borg progress (Borg outputs JSON progress to stderr)
                if decoded_line.startswith('{') and '"type":"progress"' in decoded_line:
                    try:
                        progress = json.loads(decoded_line)
                        job.current_progress = {
                            'percent': progress.get('percent', 0),
                            'nfiles': progress.get('nfiles', 0),
                            'current_file': progress.get('current', ''),
                            'original_size': progress.get('original_size', 0),
                            'compressed_size': progress.get('compressed_size', 0)
                        }
                        
                        # Broadcast progress update
                        self._broadcast_job_event({
                            "type": "job_progress",
                            "job_id": job_id,
                            "progress": job.current_progress
                        })
                    except json.JSONDecodeError:
                        pass
                
                # Broadcast output line
                self._broadcast_job_event({
                    "type": "job_output",
                    "job_id": job_id,
                    "line": decoded_line,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Wait for process to complete
            await process.wait()
            
            job.return_code = process.returncode
            job.status = 'completed' if process.returncode == 0 else 'failed'
            job.completed_at = datetime.now()
            
            logger.info(f"Borg job {job_id} completed with return code {process.returncode}")
            
            # Broadcast job completion event
            self._broadcast_job_event({
                "type": "job_completed",
                "job_id": job_id,
                "status": job.status,
                "return_code": process.returncode,
                "completed_at": job.completed_at.isoformat()
            })
            
            # Update database job record with results
            asyncio.create_task(self._update_database_job(job_id))
            
            # Auto-cleanup completed job after 30 seconds
            asyncio.create_task(self._auto_cleanup_job(job_id, delay=30))
            
        except Exception as e:
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now()
            logger.error(f"Borg job {job_id} failed: {e}")
            
            # Broadcast job failure event
            self._broadcast_job_event({
                "type": "job_failed",
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "completed_at": job.completed_at.isoformat()
            })
            
            # Update database job record with results
            asyncio.create_task(self._update_database_job(job_id))
            
            # Auto-cleanup failed job after 30 seconds
            asyncio.create_task(self._auto_cleanup_job(job_id, delay=30))
        
        finally:
            self._processes.pop(job_id, None)
    
    async def get_job_output_stream(
        self, 
        job_id: str, 
        last_n_lines: Optional[int] = None
    ) -> Dict:
        """Get current output for streaming to frontend"""
        job = self.jobs.get(job_id)
        if not job:
            return {'error': 'Job not found'}
        
        lines = list(job.output_lines)
        if last_n_lines:
            lines = lines[-last_n_lines:]
        
        return {
            'job_id': job_id,
            'status': job.status,
            'progress': job.current_progress,
            'lines': lines,
            'total_lines': len(job.output_lines),
            'return_code': job.return_code,
            'started_at': job.started_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error': job.error
        }
    
    async def stream_job_output(self, job_id: str):
        """Generator for real-time streaming (SSE/WebSocket)"""
        job = self.jobs.get(job_id)
        if not job:
            return
        
        last_sent = 0
        while job.status == 'running' or last_sent < len(job.output_lines):
            current_lines = list(job.output_lines)
            
            # Send new lines since last check
            if len(current_lines) > last_sent:
                for line in current_lines[last_sent:]:
                    yield {
                        'type': 'output',
                        'data': line,
                        'progress': job.current_progress
                    }
                last_sent = len(current_lines)
            
            if job.status != 'running':
                yield {
                    'type': 'complete',
                    'status': job.status,
                    'return_code': job.return_code
                }
                break
            
            await asyncio.sleep(0.1)  # Poll interval
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running Borg job"""
        process = self._processes.get(job_id)
        if process:
            try:
                process.terminate()
                await asyncio.sleep(2)
                if process.returncode is None:
                    process.kill()  # Force kill if not terminated
                logger.info(f"Cancelled Borg job {job_id}")
                return True
            except Exception as e:
                logger.error(f"Error cancelling job {job_id}: {e}")
                return False
        return False
    
    def _broadcast_job_event(self, event: Dict):
        """Broadcast job event to all SSE clients"""
        # Remove empty queues (disconnected clients)
        self._event_queues = [q for q in self._event_queues if not q.empty() or q.qsize() == 0]
        
        # Send event to all active queues
        for queue in self._event_queues[:]:  # Create copy to avoid modification during iteration
            try:
                if not queue.full():
                    queue.put_nowait(event)
            except:
                # Remove failed queues
                try:
                    self._event_queues.remove(queue)
                except ValueError:
                    pass
    
    def get_queue_stats(self) -> Dict:
        """Get queue and concurrency statistics"""
        running_backups = sum(1 for job in self.jobs.values() 
                             if job.status == 'running' and 'create' in job.command)
        queued_backups = sum(1 for job in self.jobs.values() 
                            if job.status == 'queued')
        
        return {
            "max_concurrent_backups": self.MAX_CONCURRENT_BACKUPS,
            "running_backups": running_backups,
            "queued_backups": queued_backups,
            "available_slots": self.MAX_CONCURRENT_BACKUPS - running_backups,
            "queue_size": self._backup_queue.qsize() if hasattr(self, '_backup_queue') else 0
        }
    
    async def stream_all_job_updates(self) -> AsyncGenerator[Dict, None]:
        """Generator for streaming all job updates via SSE"""
        # Create a queue for this client
        client_queue = asyncio.Queue(maxsize=100)
        self._event_queues.append(client_queue)
        
        try:
            while True:
                try:
                    # Wait for events with timeout
                    event = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"type": "keepalive", "timestamp": datetime.now().isoformat()}
                except Exception as e:
                    logger.error(f"SSE streaming error: {e}")
                    break
        finally:
            # Clean up this client's queue
            try:
                self._event_queues.remove(client_queue)
            except ValueError:
                pass
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get basic job status for API responses"""
        job = self.jobs.get(job_id)
        if not job:
            return None
        
        return {
            'running': job.status == 'running',
            'completed': job.status == 'completed',
            'status': job.status,
            'started_at': job.started_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'return_code': job.return_code,
            'error': job.error
        }
    
    def cleanup_job(self, job_id: str) -> bool:
        """Remove job from memory after results are retrieved"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            logger.info(f"Cleaned up job {job_id}")
            return True
        return False
    
    async def _auto_cleanup_job(self, job_id: str, delay: int = 30):
        """Auto-cleanup job after specified delay"""
        await asyncio.sleep(delay)
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status in ['completed', 'failed']:
                logger.info(f"Auto-cleaning up {job.status} job {job_id} after {delay}s")
                self.cleanup_job(job_id)
                
                # Broadcast updated jobs list
                self._broadcast_job_event({
                    "type": "jobs_update",
                    "jobs": [
                        {
                            "id": jid,
                            "status": j.status,
                            "started_at": j.started_at.isoformat(),
                            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                            "return_code": j.return_code,
                            "error": j.error,
                            "progress": j.current_progress,
                            "command": " ".join(j.command[:3]) + "..." if len(j.command) > 3 else " ".join(j.command)
                        }
                        for jid, j in self.jobs.items()
                    ]
                })
    
    async def _update_database_job(self, job_id: str):
        """Update database job record with completion results"""
        try:
            from app.models.database import Job, get_db
            from datetime import datetime
            
            job = self.jobs.get(job_id)
            if not job:
                return
            
            # Get output lines as text
            output_text = "\n".join([line['text'] for line in job.output_lines])
            
            # Update database job
            db = next(get_db())
            try:
                db_job = db.query(Job).filter(Job.job_uuid == job_id).first()
                if db_job:
                    logger.info(f"🔍 Found database job {db_job.id} for JobManager job {job_id}")
                    logger.info(f"📊 Job details - Type: {db_job.type}, Status: {job.status}, Return Code: {job.return_code}, Cloud Sync Config ID: {db_job.cloud_sync_config_id}")
                    
                    db_job.status = 'completed' if job.status == 'completed' else 'failed'
                    db_job.finished_at = job.completed_at
                    db_job.log_output = output_text
                    if job.error:
                        db_job.error = job.error
                    
                    db.commit()
                    logger.info(f"✅ Updated database job record for {job_id}")
                    
                    # Trigger cloud backup if this was a successful backup job
                    logger.info(f"🔍 Checking cloud backup trigger conditions:")
                    logger.info(f"  - job.status == 'completed': {job.status == 'completed'}")
                    logger.info(f"  - db_job.type in ['backup', 'scheduled_backup']: {db_job.type in ['backup', 'scheduled_backup']} (actual: {db_job.type})")
                    logger.info(f"  - job.return_code == 0: {job.return_code == 0}")
                    logger.info(f"  - db_job.cloud_sync_config_id: {db_job.cloud_sync_config_id}")
                    
                    if (job.status == 'completed' and 
                        db_job.type in ['backup', 'scheduled_backup'] and 
                        job.return_code == 0):
                        logger.info(f"🚀 All conditions met - triggering cloud backup for job {job_id}")
                        asyncio.create_task(self._trigger_cloud_backups(db_job, db))
                    else:
                        logger.info(f"❌ Cloud backup conditions not met for job {job_id}")
                        
                else:
                    logger.warning(f"No database job found for UUID {job_id}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to update database job for {job_id}: {e}")
    
    async def _trigger_cloud_backups(self, db_job: 'Job', db: 'Session'):
        """Trigger cloud backup for the specific configuration selected in the job after a successful borg backup"""
        logger.info(f"☁️ _trigger_cloud_backups called for job {db_job.id}")
        
        try:
            from app.models.database import CloudSyncConfig, Repository
            from app.services.rclone_service import rclone_service
            from app.api.sync import sync_repository_task
            
            # Only trigger cloud backup if a specific configuration was selected for this job
            if not db_job.cloud_sync_config_id:
                logger.info(f"🔍 No cloud sync configuration selected for job {db_job.id}")
                return
            
            logger.info(f"🔍 Looking for cloud sync configuration {db_job.cloud_sync_config_id}")
            
            # Get the specific cloud sync configuration
            cloud_config = db.query(CloudSyncConfig).filter(
                CloudSyncConfig.id == db_job.cloud_sync_config_id,
                CloudSyncConfig.enabled == True
            ).first()
            
            if not cloud_config:
                logger.warning(f"⚠️ Cloud sync configuration {db_job.cloud_sync_config_id} not found or disabled for job {db_job.id}")
                return
            
            logger.info(f"✅ Found cloud backup configuration: {cloud_config.name} (enabled: {cloud_config.enabled})")
            
            # Get the repository that was backed up
            logger.info(f"🔍 Looking for repository {db_job.repository_id}")
            repository = db.query(Repository).filter(
                Repository.id == db_job.repository_id
            ).first()
            
            if not repository:
                logger.error(f"⚠️ Repository not found for job {db_job.id}")
                return
            
            logger.info(f"✅ Found repository: {repository.name}")
            logger.info(f"🚀 Triggering cloud backup to '{cloud_config.name}' for repository '{repository.name}' after successful borg backup")
            
            # Create cloud backup job for the specific configuration
            try:
                # Create a new sync job
                from app.models.database import Job as JobModel
                
                logger.info(f"📝 Creating sync job in database")
                sync_job = JobModel(
                    repository_id=repository.id,
                    type="sync",
                    status="pending"
                )
                db.add(sync_job)
                db.commit()
                db.refresh(sync_job)
                
                logger.info(f"✅ Created sync job {sync_job.id}")
                logger.info(f"🚀 Starting cloud backup task with parameters:")
                logger.info(f"  - repository_id: {repository.id}")
                logger.info(f"  - config_name: {cloud_config.name}")
                logger.info(f"  - bucket_name: {cloud_config.bucket_name}")
                logger.info(f"  - path_prefix: {cloud_config.path_prefix or ''}")
                logger.info(f"  - sync_job_id: {sync_job.id}")
                
                # Start the sync task in the background
                task = asyncio.create_task(sync_repository_task(
                    repository.id,
                    cloud_config.name,  # config name
                    cloud_config.bucket_name,
                    cloud_config.path_prefix or "",
                    sync_job.id
                ))
                
                logger.info(f"✅ Cloud backup task started successfully for '{cloud_config.name}'")
                
            except Exception as e:
                logger.error(f"❌ Failed to create cloud backup job for config '{cloud_config.name}': {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                    
        except Exception as e:
            logger.error(f"Failed to trigger cloud backups: {e}")

# Global job manager instance
borg_job_manager = BorgJobManager()