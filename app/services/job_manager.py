import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, List
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
        
    async def start_borg_command(
        self, 
        command: List[str],
        env: Optional[Dict] = None
    ) -> str:
        """Start a Borg command and track its output"""
        job_id = str(uuid.uuid4())
        
        job = BorgJob(
            id=job_id,
            command=command,
            status='running',
            started_at=datetime.now()
        )
        self.jobs[job_id] = job
        
        logger.info(f"Starting Borg job {job_id} with command: {' '.join(command)}")
        
        # Start the subprocess with output streaming
        asyncio.create_task(self._run_borg_job(job_id, command, env))
        
        return job_id
    
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
                    except json.JSONDecodeError:
                        pass
            
            # Wait for process to complete
            await process.wait()
            
            job.return_code = process.returncode
            job.status = 'completed' if process.returncode == 0 else 'failed'
            job.completed_at = datetime.now()
            
            logger.info(f"Borg job {job_id} completed with return code {process.returncode}")
            
        except Exception as e:
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now()
            logger.error(f"Borg job {job_id} failed: {e}")
        
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

# Global job manager instance
borg_job_manager = BorgJobManager()