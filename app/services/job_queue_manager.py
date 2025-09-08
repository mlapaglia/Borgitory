"""
Job Queue Manager - Handles job queuing and concurrency control
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class JobPriority(Enum):
    """Job priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class QueuedJob:
    """Represents a job in the queue"""
    job_id: str
    job_type: str
    priority: JobPriority = JobPriority.NORMAL
    queued_at: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.queued_at is None:
            self.queued_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}


@dataclass 
class QueueStats:
    """Queue statistics"""
    total_queued: int
    running_jobs: int
    max_concurrent: int
    available_slots: int
    queue_size_by_type: Dict[str, int]


class JobQueueManager:
    """Manages job queuing and concurrency control"""
    
    def __init__(
        self,
        max_concurrent_backups: int = 5,
        max_concurrent_operations: int = 10,
        queue_poll_interval: float = 0.1
    ):
        self.max_concurrent_backups = max_concurrent_backups
        self.max_concurrent_operations = max_concurrent_operations
        self.queue_poll_interval = queue_poll_interval
        
        # Separate queues for different job types
        self._backup_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._operation_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        
        # Semaphores for concurrency control
        self._backup_semaphore: Optional[asyncio.Semaphore] = None
        self._operation_semaphore: Optional[asyncio.Semaphore] = None
        
        # Running job tracking
        self._running_jobs: Dict[str, QueuedJob] = {}
        self._running_backups: Dict[str, QueuedJob] = {}
        
        # Queue processor control
        self._queue_processors_started = False
        self._shutdown_requested = False
        
        # Callbacks for job events
        self._job_start_callback: Optional[Callable[[str, QueuedJob], None]] = None
        self._job_complete_callback: Optional[Callable[[str, bool], None]] = None
    
    async def initialize(self):
        """Initialize async resources"""
        if self._backup_semaphore is None:
            self._backup_semaphore = asyncio.Semaphore(self.max_concurrent_backups)
            self._operation_semaphore = asyncio.Semaphore(self.max_concurrent_operations)
            
            logger.info(
                f"Queue manager initialized - max concurrent backups: {self.max_concurrent_backups}, "
                f"max concurrent operations: {self.max_concurrent_operations}"
            )
    
    def set_callbacks(
        self,
        job_start_callback: Optional[Callable[[str, QueuedJob], None]] = None,
        job_complete_callback: Optional[Callable[[str, bool], None]] = None
    ):
        """Set callbacks for job lifecycle events"""
        self._job_start_callback = job_start_callback
        self._job_complete_callback = job_complete_callback
    
    async def enqueue_job(
        self,
        job_id: str,
        job_type: str,
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a job to the appropriate queue"""
        await self.initialize()
        
        queued_job = QueuedJob(
            job_id=job_id,
            job_type=job_type,
            priority=priority,
            metadata=metadata or {}
        )
        
        # Determine which queue to use
        is_backup = self._is_backup_job(job_type)
        queue = self._backup_queue if is_backup else self._operation_queue
        
        # Priority queue uses negative priority for correct ordering (higher priority = lower number)
        priority_value = -priority.value
        await queue.put((priority_value, queued_job.queued_at, queued_job))
        
        logger.info(
            f"Queued {job_type} job {job_id} with priority {priority.name} "
            f"in {'backup' if is_backup else 'operation'} queue"
        )
        
        # Start queue processors if not already running
        if not self._queue_processors_started:
            await self._start_queue_processors()
        
        return True
    
    async def _start_queue_processors(self):
        """Start the queue processor tasks"""
        if not self._queue_processors_started:
            asyncio.create_task(self._process_backup_queue())
            asyncio.create_task(self._process_operation_queue())
            self._queue_processors_started = True
            logger.info("Queue processors started")
    
    async def _process_backup_queue(self):
        """Process backup jobs with concurrency control"""
        logger.info("Backup queue processor started")
        
        while not self._shutdown_requested:
            try:
                # Get next job from queue with timeout
                try:
                    _, _, queued_job = await asyncio.wait_for(
                        self._backup_queue.get(),
                        timeout=self.queue_poll_interval * 10
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Acquire semaphore (blocks if at max concurrency)
                await self._backup_semaphore.acquire()
                
                try:
                    # Track as running
                    self._running_backups[queued_job.job_id] = queued_job
                    self._running_jobs[queued_job.job_id] = queued_job
                    
                    logger.info(f"Starting backup job {queued_job.job_id}")
                    
                    # Notify job start
                    if self._job_start_callback:
                        self._job_start_callback(queued_job.job_id, queued_job)
                    
                    # Create task to handle job execution and cleanup
                    asyncio.create_task(
                        self._execute_and_cleanup_job(queued_job, is_backup=True)
                    )
                    
                except Exception as e:
                    logger.error(f"Error starting backup job {queued_job.job_id}: {e}")
                    self._backup_semaphore.release()
                    self._cleanup_running_job(queued_job.job_id, is_backup=True)
                    
            except Exception as e:
                logger.error(f"Error in backup queue processor: {e}")
                await asyncio.sleep(1)
    
    async def _process_operation_queue(self):
        """Process operation jobs with concurrency control"""
        logger.info("Operation queue processor started")
        
        while not self._shutdown_requested:
            try:
                # Get next job from queue with timeout
                try:
                    _, _, queued_job = await asyncio.wait_for(
                        self._operation_queue.get(),
                        timeout=self.queue_poll_interval * 10
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Acquire semaphore (blocks if at max concurrency)
                await self._operation_semaphore.acquire()
                
                try:
                    # Track as running
                    self._running_jobs[queued_job.job_id] = queued_job
                    
                    logger.info(f"Starting operation job {queued_job.job_id}")
                    
                    # Notify job start
                    if self._job_start_callback:
                        self._job_start_callback(queued_job.job_id, queued_job)
                    
                    # Create task to handle job execution and cleanup
                    asyncio.create_task(
                        self._execute_and_cleanup_job(queued_job, is_backup=False)
                    )
                    
                except Exception as e:
                    logger.error(f"Error starting operation job {queued_job.job_id}: {e}")
                    self._operation_semaphore.release()
                    self._cleanup_running_job(queued_job.job_id, is_backup=False)
                    
            except Exception as e:
                logger.error(f"Error in operation queue processor: {e}")
                await asyncio.sleep(1)
    
    async def _execute_and_cleanup_job(self, queued_job: QueuedJob, is_backup: bool):
        """Execute job and clean up resources when complete"""
        job_id = queued_job.job_id
        success = False
        
        try:
            # Job execution happens in the main job manager
            # This is just a placeholder - actual execution is handled elsewhere
            logger.debug(f"Job {job_id} execution delegated to job manager")
            
            # Wait for job completion (this would be handled by job status updates)
            # For now, we'll just mark as successful
            success = True
            
        except Exception as e:
            logger.error(f"Error executing job {job_id}: {e}")
            success = False
        
        finally:
            # Clean up resources
            if is_backup:
                self._backup_semaphore.release()
            else:
                self._operation_semaphore.release()
            
            self._cleanup_running_job(job_id, is_backup)
            
            # Notify job completion
            if self._job_complete_callback:
                self._job_complete_callback(job_id, success)
    
    def _cleanup_running_job(self, job_id: str, is_backup: bool):
        """Clean up tracking for a running job"""
        if job_id in self._running_jobs:
            del self._running_jobs[job_id]
        
        if is_backup and job_id in self._running_backups:
            del self._running_backups[job_id]
    
    def _is_backup_job(self, job_type: str) -> bool:
        """Determine if a job type is a backup job"""
        backup_types = ["backup", "manual_backup", "scheduled_backup", "create"]
        return any(backup_type in job_type.lower() for backup_type in backup_types)
    
    def get_queue_stats(self) -> QueueStats:
        """Get current queue statistics"""
        backup_queue_size = self._backup_queue.qsize() if self._backup_queue else 0
        operation_queue_size = self._operation_queue.qsize() if self._operation_queue else 0
        
        running_backups = len(self._running_backups)
        total_running = len(self._running_jobs)
        
        return QueueStats(
            total_queued=backup_queue_size + operation_queue_size,
            running_jobs=total_running,
            max_concurrent=max(self.max_concurrent_backups, self.max_concurrent_operations),
            available_slots=max(0, self.max_concurrent_backups - running_backups),
            queue_size_by_type={
                "backup": backup_queue_size,
                "operation": operation_queue_size
            }
        )
    
    def get_running_jobs(self) -> List[Dict[str, Any]]:
        """Get list of currently running jobs"""
        return [
            {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "priority": job.priority.name,
                "queued_at": job.queued_at.isoformat(),
                "metadata": job.metadata
            }
            for job in self._running_jobs.values()
        ]
    
    async def shutdown(self):
        """Shutdown queue processors and clean up"""
        logger.info("Shutting down job queue manager")
        self._shutdown_requested = True
        
        # Clear queues
        while not self._backup_queue.empty():
            try:
                self._backup_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        while not self._operation_queue.empty():
            try:
                self._operation_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Clear running jobs
        self._running_jobs.clear()
        self._running_backups.clear()
        
        logger.info("Job queue manager shutdown complete")