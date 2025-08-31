import asyncio
import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.models.database import Repository, Job, get_db
from app.models.schemas import Job as JobSchema, BackupRequest
from app.services.borg_service import borg_service
from app.services.job_manager import borg_job_manager

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.post("/backup")
async def create_backup(
    backup_request: BackupRequest, 
    db: Session = Depends(get_db)
):
    """Start a backup job and return job_id for tracking"""
    repository = db.query(Repository).filter(
        Repository.id == backup_request.repository_id
    ).first()
    
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        # Start the backup using the new JobManager system
        borg_job_id = await borg_service.create_backup(
            repository=repository,
            source_path=backup_request.source_path,
            compression=backup_request.compression,
            dry_run=backup_request.dry_run,
            cloud_backup_config_id=backup_request.cloud_backup_config_id
        )
        
        return {"job_id": borg_job_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Failed to start backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start backup: {str(e)}")


@router.get("/stream")
async def stream_all_jobs():
    """Stream real-time updates for all jobs via Server-Sent Events"""
    async def event_generator():
        try:
            # Send initial job list
            jobs_data = []
            for job_id, borg_job in borg_job_manager.jobs.items():
                jobs_data.append({
                    "id": job_id,
                    "type": "job_status",
                    "status": borg_job.status,
                    "started_at": borg_job.started_at.isoformat(),
                    "completed_at": borg_job.completed_at.isoformat() if borg_job.completed_at else None,
                    "return_code": borg_job.return_code,
                    "error": borg_job.error,
                    "progress": borg_job.current_progress,
                    "command": " ".join(borg_job.command[:3]) + "..." if len(borg_job.command) > 3 else " ".join(borg_job.command)
                })
            
            if jobs_data:
                yield f"event: jobs_update\ndata: {json.dumps({'type': 'jobs_update', 'jobs': jobs_data})}\n\n"
            else:
                yield f"event: jobs_update\ndata: {json.dumps({'type': 'jobs_update', 'jobs': []})}\n\n"
            
            # Stream job updates
            async for event in borg_job_manager.stream_all_job_updates():
                event_type = event.get('type', 'unknown')
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                
        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        }
    )

@router.get("/")
def list_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List database job records (legacy jobs) and active JobManager jobs"""
    
    # Get database jobs (legacy) with repository relationship loaded
    db_jobs = db.query(Job).options(joinedload(Job.repository)).order_by(Job.id.desc()).offset(skip).limit(limit).all()
    
    # Convert to dict format and add JobManager jobs
    jobs_list = []
    
    # Add database jobs
    for job in db_jobs:
        repository_name = "Unknown"
        if job.repository_id and job.repository:
            repository_name = job.repository.name
        
        jobs_list.append({
            "id": job.id,
            "job_id": str(job.id),  # Use primary key as job_id
            "repository_id": job.repository_id,
            "repository_name": repository_name,
            "type": job.type,
            "status": job.status,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error": job.error,
            "log_output": job.log_output,
            "source": "database"
        })
    
    # Add active JobManager jobs
    for job_id, borg_job in borg_job_manager.jobs.items():
        # Skip if this job is already in database
        existing_db_job = next((j for j in db_jobs if str(j.id) == job_id), None)
        if existing_db_job:
            continue
        
        # Try to find the repository name from command if possible
        repository_name = "Unknown"
        job_type = "unknown"
        
        # Try to infer type from command
        if borg_job.command and len(borg_job.command) > 1:
            if "create" in borg_job.command:
                job_type = "backup"
            elif "list" in borg_job.command:
                job_type = "list"
            elif "check" in borg_job.command:
                job_type = "verify"
        
        jobs_list.append({
            "id": f"jm_{job_id}",  # Prefix to distinguish from DB IDs
            "job_id": job_id,
            "repository_id": None,  # JobManager doesn't track this separately
            "repository_name": repository_name,
            "type": job_type,
            "status": borg_job.status,
            "started_at": borg_job.started_at.isoformat(),
            "finished_at": borg_job.completed_at.isoformat() if borg_job.completed_at else None,
            "error": borg_job.error,
            "log_output": None,  # JobManager output is in-memory only
            "source": "jobmanager"
        })
    
    return jobs_list


@router.get("/html", response_class=HTMLResponse)
def get_jobs_html(request: Request, db: Session = Depends(get_db)):
    """Get job history as HTML"""
    try:
        # Get recent jobs (last 20)
        db_jobs = db.query(Job).options(joinedload(Job.repository)).order_by(Job.id.desc()).limit(20).all()
        
        html_content = ""
        
        if not db_jobs:
            html_content = '''
                <div class="text-gray-500 text-center py-8">
                    <p>No job history available.</p>
                </div>
            '''
        else:
            html_content = '<div class="space-y-3">'
            
            for job in db_jobs:
                repository_name = job.repository.name if job.repository else "Unknown"
                
                # Status styling
                if job.status == "completed":
                    status_class = "bg-green-100 text-green-800"
                    status_icon = "✓"
                elif job.status == "failed":
                    status_class = "bg-red-100 text-red-800"
                    status_icon = "✗"
                elif job.status == "running":
                    status_class = "bg-blue-100 text-blue-800"
                    status_icon = "⟳"
                else:
                    status_class = "bg-gray-100 text-gray-800"
                    status_icon = "◦"
                
                # Format dates
                started_at = job.started_at.strftime("%Y-%m-%d %H:%M") if job.started_at else "N/A"
                finished_at = job.finished_at.strftime("%Y-%m-%d %H:%M") if job.finished_at else "N/A"
                
                html_content += f'''
                    <div class="border rounded-lg p-4 bg-white hover:bg-gray-50">
                        <div class="flex items-center justify-between">
                            <div class="flex-1">
                                <div class="flex items-center space-x-3">
                                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium {status_class}">
                                        {status_icon} {job.status.title()}
                                    </span>
                                    <span class="text-sm font-medium text-gray-900">
                                        {job.type.title()} - {repository_name}
                                    </span>
                                </div>
                                <div class="mt-2 text-xs text-gray-500 space-x-4">
                                    <span>Started: {started_at}</span>
                                    {f'<span>Finished: {finished_at}</span>' if job.finished_at else ''}
                                    {f'<span class="text-red-600">Error: {job.error}</span>' if job.error else ''}
                                </div>
                            </div>
                            <div class="flex-shrink-0">
                                <span class="text-sm text-gray-500">#{job.id}</span>
                            </div>
                        </div>
                    </div>
                '''
            
            html_content += '</div>'
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        error_html = f'''
            <div class="text-red-500 text-center py-4">
                <p>Error loading job history: {str(e)}</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


@router.get("/current/html", response_class=HTMLResponse)
def get_current_jobs_html(request: Request):
    """Get current running jobs as HTML"""
    try:
        current_jobs = []
        
        # Get current jobs from JobManager
        for job_id, borg_job in borg_job_manager.jobs.items():
            if borg_job.status == 'running':
                # Determine job type from command
                job_type = "unknown"
                if borg_job.command and len(borg_job.command) > 1:
                    if "create" in borg_job.command:
                        job_type = "backup"
                    elif "list" in borg_job.command:
                        job_type = "list"
                    elif "check" in borg_job.command:
                        job_type = "verify"
                
                current_jobs.append({
                    'id': job_id,
                    'type': job_type,
                    'status': borg_job.status,
                    'started_at': borg_job.started_at.strftime("%H:%M:%S"),
                    'progress': borg_job.current_progress
                })
        
        html_content = ""
        
        if not current_jobs:
            html_content = '''
                <div class="text-gray-500 text-center py-4">
                    <p>No operations currently running.</p>
                </div>
            '''
        else:
            html_content = '<div class="space-y-3">'
            
            for job in current_jobs:
                progress_info = ""
                if job['progress']:
                    if 'files' in job['progress']:
                        progress_info = f"Files: {job['progress']['files']}"
                    if 'transferred' in job['progress']:
                        progress_info += f" | {job['progress']['transferred']}"
                
                html_content += f'''
                    <div class="border border-blue-200 rounded-lg p-3 bg-blue-50">
                        <div class="flex items-center">
                            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-3"></div>
                            <div class="flex-1">
                                <div class="flex items-center space-x-2">
                                    <span class="font-medium text-blue-900">{job['type'].title()}</span>
                                    <span class="text-blue-700 text-sm">#{job['id'][:8]}...</span>
                                </div>
                                <div class="text-xs text-blue-600 mt-1">
                                    Started: {job['started_at']} {f'| {progress_info}' if progress_info else ''}
                                </div>
                            </div>
                        </div>
                    </div>
                '''
            
            html_content += '</div>'
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        error_html = f'''
            <div class="text-red-500 text-center py-4">
                <p>Error loading current operations: {str(e)}</p>
            </div>
        '''
        return HTMLResponse(content=error_html)


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get job details - supports both database IDs and JobManager IDs"""
    
    # Try to get from JobManager first (if it's a UUID format)
    if len(job_id) > 10:  # Probably a UUID
        status = borg_job_manager.get_job_status(job_id)
        if status:
            return {
                "id": f"jm_{job_id}",
                "job_id": job_id,
                "repository_id": None,
                "type": "unknown",
                "status": status['status'],
                "started_at": status['started_at'],
                "finished_at": status['completed_at'],
                "error": status['error'],
                "source": "jobmanager"
            }
    
    # Try database lookup
    try:
        db_job_id = int(job_id)
        job = db.query(Job).options(joinedload(Job.repository)).filter(Job.id == db_job_id).first()
        if job:
            repository_name = "Unknown"
            if job.repository_id and job.repository:
                repository_name = job.repository.name
                
            return {
                "id": job.id,
                "job_id": str(job.id),  # Use primary key as job_id
                "repository_id": job.repository_id,
                "repository_name": repository_name,
                "type": job.type,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "error": job.error,
                "log_output": job.log_output,
                "source": "database"
            }
    except ValueError:
        pass
    
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    """Get current job status and progress"""
    output = await borg_job_manager.get_job_output_stream(job_id, last_n_lines=50)
    
    if 'error' in output:
        raise HTTPException(status_code=404, detail=output['error'])
    
    return output


@router.get("/{job_id}/output")
async def get_job_output(job_id: str, last_n_lines: int = 100):
    """Get job output lines"""
    output = await borg_job_manager.get_job_output_stream(job_id, last_n_lines=last_n_lines)
    
    if 'error' in output:
        raise HTTPException(status_code=404, detail=output['error'])
    
    return output

@router.get("/{job_id}/stream")
async def stream_job_output(job_id: str):
    """Stream real-time job output via Server-Sent Events"""
    async def event_generator():
        try:
            async for event in borg_job_manager.stream_job_output(job_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.delete("/{job_id}")
async def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """Cancel a running job"""
    
    # Try to cancel in JobManager first
    if len(job_id) > 10:  # Probably a UUID
        success = await borg_job_manager.cancel_job(job_id)
        if success:
            return {"message": "Job cancelled successfully"}
    
    # Try database job
    try:
        db_job_id = int(job_id)
        job = db.query(Job).options(joinedload(Job.repository)).filter(Job.id == db_job_id).first()
        if job:
            # Try to cancel the associated JobManager job
            # Note: Database jobs and JobManager jobs are separate systems
            # Database jobs don't directly map to JobManager UUIDs
            
            # Update database status
            job.status = "cancelled"
            job.finished_at = datetime.utcnow()
            db.commit()
            
            return {"message": "Job cancelled successfully"}
    except ValueError:
        pass
    
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/manager/stats")
def get_job_manager_stats():
    """Get JobManager statistics"""
    jobs = borg_job_manager.jobs
    running_jobs = [job for job in jobs.values() if job.status == 'running']
    completed_jobs = [job for job in jobs.values() if job.status == 'completed']
    failed_jobs = [job for job in jobs.values() if job.status == 'failed']
    
    return {
        "total_jobs": len(jobs),
        "running_jobs": len(running_jobs),
        "completed_jobs": len(completed_jobs),
        "failed_jobs": len(failed_jobs),
        "active_processes": len(borg_job_manager._processes),
        "running_job_ids": [job.id for job in running_jobs]
    }


@router.post("/manager/cleanup")
def cleanup_completed_jobs():
    """Clean up completed jobs from JobManager memory"""
    cleaned = 0
    jobs_to_remove = []
    
    for job_id, job in borg_job_manager.jobs.items():
        if job.status in ['completed', 'failed']:
            jobs_to_remove.append(job_id)
    
    for job_id in jobs_to_remove:
        borg_job_manager.cleanup_job(job_id)
        cleaned += 1
    
    return {"message": f"Cleaned up {cleaned} completed jobs"}


@router.get("/queue/stats")
def get_queue_stats():
    """Get backup queue statistics"""
    return borg_job_manager.get_queue_stats()


@router.post("/migrate")
def run_database_migration(db: Session = Depends(get_db)):
    """Manually trigger database migration for jobs table"""
    try:
        from app.models.database import migrate_job_table
        migrate_job_table()
        return {"message": "Database migration completed successfully"}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")