import asyncio
import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.models.database import Repository, Job, JobTask, get_db
from app.models.schemas import Job as JobSchema, BackupRequest, PruneRequest, CheckRequest
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
        # Import composite job manager
        from app.services.composite_job_manager import composite_job_manager
        
        # Define the tasks for this manual backup job
        task_definitions = [
            {
                'type': 'backup', 
                'name': f'Backup {repository.name}',
                'source_path': backup_request.source_path,
                'compression': backup_request.compression,
                'dry_run': backup_request.dry_run
            }
        ]
        
        # Add prune task if cleanup is configured
        if backup_request.cleanup_config_id:
            from app.models.database import CleanupConfig
            cleanup_config = db.query(CleanupConfig).filter(
                CleanupConfig.id == backup_request.cleanup_config_id,
                CleanupConfig.enabled == True
            ).first()
            
            if cleanup_config:
                prune_task = {
                    'type': 'prune', 
                    'name': f'Clean up {repository.name}',
                    'dry_run': False,  # Don't dry run when chained after backup
                    'show_list': cleanup_config.show_list,
                    'show_stats': cleanup_config.show_stats,
                    'save_space': cleanup_config.save_space
                }
                
                # Add retention parameters based on strategy
                if cleanup_config.strategy == "simple" and cleanup_config.keep_within_days:
                    prune_task['keep_within'] = f"{cleanup_config.keep_within_days}d"
                elif cleanup_config.strategy == "advanced":
                    if cleanup_config.keep_daily:
                        prune_task['keep_daily'] = cleanup_config.keep_daily
                    if cleanup_config.keep_weekly:
                        prune_task['keep_weekly'] = cleanup_config.keep_weekly
                    if cleanup_config.keep_monthly:
                        prune_task['keep_monthly'] = cleanup_config.keep_monthly
                    if cleanup_config.keep_yearly:
                        prune_task['keep_yearly'] = cleanup_config.keep_yearly
                
                task_definitions.append(prune_task)
        
        # Add cloud sync task if cloud backup is configured
        if backup_request.cloud_sync_config_id:
            task_definitions.append({
                'type': 'cloud_sync', 
                'name': f'Sync to Cloud'
            })
        
        # Add check task if repository check is configured
        if backup_request.check_config_id:
            from app.models.database import RepositoryCheckConfig
            check_config = db.query(RepositoryCheckConfig).filter(
                RepositoryCheckConfig.id == backup_request.check_config_id,
                RepositoryCheckConfig.enabled == True
            ).first()
            
            if check_config:
                check_task = {
                    'type': 'check',
                    'name': f'Check {repository.name} ({check_config.name})',
                    'check_type': check_config.check_type,
                    'verify_data': check_config.verify_data,
                    'repair_mode': check_config.repair_mode,
                    'save_space': check_config.save_space,
                    'max_duration': check_config.max_duration,
                    'archive_prefix': check_config.archive_prefix,
                    'archive_glob': check_config.archive_glob,
                    'first_n_archives': check_config.first_n_archives,
                    'last_n_archives': check_config.last_n_archives
                }
                task_definitions.append(check_task)
        
        # Create composite job
        job_id = await composite_job_manager.create_composite_job(
            job_type="manual_backup",
            task_definitions=task_definitions,
            repository=repository,
            schedule=None,  # No schedule for manual backups
            cloud_sync_config_id=backup_request.cloud_sync_config_id
        )
        
        return {"job_id": job_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Failed to start backup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start backup: {str(e)}")


@router.post("/prune")
async def create_prune_job(
    prune_request: PruneRequest, 
    db: Session = Depends(get_db)
):
    """Start an archive pruning job and return job_id for tracking"""
    repository = db.query(Repository).filter(
        Repository.id == prune_request.repository_id
    ).first()
    
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    try:
        # Import composite job manager
        from app.services.composite_job_manager import composite_job_manager
        
        # Build task definition based on strategy
        task_def = {
            'type': 'prune', 
            'name': f'Prune {repository.name}',
            'dry_run': prune_request.dry_run,
            'show_list': prune_request.show_list,
            'show_stats': prune_request.show_stats,
            'save_space': prune_request.save_space,
            'force_prune': prune_request.force_prune
        }
        
        # Add retention parameters based on strategy
        if prune_request.strategy == "simple" and prune_request.keep_within_days:
            task_def['keep_within'] = f"{prune_request.keep_within_days}d"
        elif prune_request.strategy == "advanced":
            if prune_request.keep_daily:
                task_def['keep_daily'] = prune_request.keep_daily
            if prune_request.keep_weekly:
                task_def['keep_weekly'] = prune_request.keep_weekly
            if prune_request.keep_monthly:
                task_def['keep_monthly'] = prune_request.keep_monthly
            if prune_request.keep_yearly:
                task_def['keep_yearly'] = prune_request.keep_yearly
        
        task_definitions = [task_def]
        
        # Create composite job
        job_id = await composite_job_manager.create_composite_job(
            job_type="prune",
            task_definitions=task_definitions,
            repository=repository,
            schedule=None
        )
        
        return {"job_id": job_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Failed to start prune job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start prune job: {str(e)}")


@router.post("/check")
async def create_check_job(
    check_request: CheckRequest, 
    db: Session = Depends(get_db)
):
    """Start a repository check job and return job_id for tracking"""
    repository = db.query(Repository).filter(
        Repository.id == check_request.repository_id
    ).first()
    
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Import here to avoid circular imports
    from app.models.database import RepositoryCheckConfig
    
    try:
        # Import composite job manager
        from app.services.composite_job_manager import composite_job_manager
        
        # Determine check parameters - either from policy or custom
        if check_request.check_config_id:
            # Use existing check policy
            check_config = db.query(RepositoryCheckConfig).filter(
                RepositoryCheckConfig.id == check_request.check_config_id
            ).first()
            
            if not check_config:
                raise HTTPException(status_code=404, detail="Check policy not found")
            
            if not check_config.enabled:
                raise HTTPException(status_code=400, detail="Check policy is disabled")
                
            # Use policy parameters
            task_def = {
                'type': 'check',
                'name': f'Check {repository.name} ({check_config.name})',
                'check_type': check_config.check_type,
                'verify_data': check_config.verify_data,
                'repair_mode': check_config.repair_mode,
                'save_space': check_config.save_space,
                'max_duration': check_config.max_duration,
                'archive_prefix': check_config.archive_prefix,
                'archive_glob': check_config.archive_glob,
                'first_n_archives': check_config.first_n_archives,
                'last_n_archives': check_config.last_n_archives
            }
        else:
            # Use custom parameters
            task_def = {
                'type': 'check',
                'name': f'Check {repository.name}',
                'check_type': check_request.check_type,
                'verify_data': check_request.verify_data,
                'repair_mode': check_request.repair_mode,
                'save_space': check_request.save_space,
                'max_duration': check_request.max_duration,
                'archive_prefix': check_request.archive_prefix,
                'archive_glob': check_request.archive_glob,
                'first_n_archives': check_request.first_n_archives,
                'last_n_archives': check_request.last_n_archives
            }
        
        task_definitions = [task_def]
        
        # Start the composite job
        job_id = await composite_job_manager.create_composite_job(
            job_type="check",
            task_definitions=task_definitions,
            repository=repository,
            schedule=None
        )
        
        return {"job_id": job_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Failed to start check job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start check job: {str(e)}")


@router.get("/stream")
async def stream_all_jobs():
    """Stream real-time updates for all jobs via Server-Sent Events"""
    async def event_generator():
        try:
            from app.services.composite_job_manager import composite_job_manager
            
            # Send initial job list (both regular and composite jobs)
            jobs_data = []
            
            # Add regular borg jobs
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
            
            # Add composite jobs
            for job_id, composite_job in composite_job_manager.jobs.items():
                jobs_data.append({
                    "id": job_id,
                    "type": "composite_job_status",
                    "status": composite_job.status,
                    "started_at": composite_job.started_at.isoformat(),
                    "completed_at": composite_job.completed_at.isoformat() if composite_job.completed_at else None,
                    "current_task_index": composite_job.current_task_index,
                    "total_tasks": len(composite_job.tasks),
                    "job_type": composite_job.job_type
                })
            
            if jobs_data:
                yield f"event: jobs_update\ndata: {json.dumps({'type': 'jobs_update', 'jobs': jobs_data})}\n\n"
            else:
                yield f"event: jobs_update\ndata: {json.dumps({'type': 'jobs_update', 'jobs': []})}\n\n"
            
            # Stream job updates from borg job manager only
            # Individual task output should come from /api/jobs/{job_id}/stream
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
def list_jobs(skip: int = 0, limit: int = 100, type: str = None, db: Session = Depends(get_db)):
    """List database job records (legacy jobs) and active JobManager jobs"""
    
    # Get database jobs (legacy) with repository relationship loaded
    query = db.query(Job).options(joinedload(Job.repository))
    
    # Filter by type if provided
    if type:
        query = query.filter(Job.type == type)
        
    db_jobs = query.order_by(Job.id.desc()).offset(skip).limit(limit).all()
    
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
def get_jobs_html(request: Request, expand: str = None, db: Session = Depends(get_db)):
    """Get job history as HTML"""
    try:
        # Get recent jobs (last 20) with their tasks
        db_jobs = db.query(Job).options(
            joinedload(Job.repository),
            joinedload(Job.tasks)
        ).order_by(Job.id.desc()).limit(20).all()
        
        html_content = ""
        
        if not db_jobs:
            html_content = templates.get_template("partials/jobs/empty_state.html").render(
                message="No job history available.",
                padding="8"
            )
        else:
            html_content = '<div class="space-y-3">'
            
            for job in db_jobs:
                should_expand = (expand and (str(job.id) == expand or (job.job_uuid and job.job_uuid.startswith(expand[:8]))))
                html_content += render_job_html(job, expand_details=should_expand)
            
            html_content += '</div>'
        
        return html_content
        
    except Exception as e:
        logger.error(f"Error generating jobs HTML: {e}")
        return templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading jobs: {str(e)}",
            padding="4"
        )


def render_job_html(job, expand_details=False):
    """Render HTML for a single job (simple or composite)"""
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
    
    # Check if this is a composite job
    is_composite = job.job_type == "composite" and job.tasks
    
    # Job header
    job_title = f"{job.type.replace('_', ' ').title()} - {repository_name}"
    if is_composite:
        progress_text = f"({job.completed_tasks}/{job.total_tasks} tasks)"
        job_title += f" {progress_text}"
    
    # Sort tasks by order if composite
    sorted_tasks = sorted(job.tasks, key=lambda t: t.task_order) if is_composite else []
    
    # Render the template with context
    return templates.get_template("partials/jobs/job_item.html").render(
        job=job,
        repository_name=repository_name,
        status_class=status_class,
        status_icon=status_icon,
        started_at=started_at,
        finished_at=finished_at,
        job_title=job_title,
        is_composite=is_composite,
        sorted_tasks=sorted_tasks,
        expand_details=expand_details
    )


@router.get("/current/html", response_class=HTMLResponse)
def get_current_jobs_html(request: Request):
    """Get current running jobs as HTML"""
    try:
        current_jobs = []
        
        # Get current jobs from JobManager (simple borg jobs)
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
                
                # Calculate progress info
                progress_info = ""
                if borg_job.current_progress:
                    if 'files' in borg_job.current_progress:
                        progress_info = f"Files: {borg_job.current_progress['files']}"
                    if 'transferred' in borg_job.current_progress:
                        progress_info += f" | {borg_job.current_progress['transferred']}"
                
                current_jobs.append({
                    'id': job_id,
                    'type': job_type,
                    'status': borg_job.status,
                    'started_at': borg_job.started_at.strftime("%H:%M:%S"),
                    'progress': borg_job.current_progress,
                    'progress_info': progress_info
                })
        
        # Get current composite jobs from CompositeJobManager
        from app.services.composite_job_manager import composite_job_manager
        for job_id, composite_job in composite_job_manager.jobs.items():
            if composite_job.status == 'running':
                # Get current task info
                current_task = None
                if composite_job.current_task_index < len(composite_job.tasks):
                    current_task = composite_job.tasks[composite_job.current_task_index]
                
                progress_info = f"Task: {current_task.task_name if current_task else 'Unknown'} ({composite_job.current_task_index + 1}/{len(composite_job.tasks)})"
                
                current_jobs.append({
                    'id': job_id,
                    'type': composite_job.job_type,
                    'status': composite_job.status,
                    'started_at': composite_job.started_at.strftime("%H:%M:%S"),
                    'progress': {
                        'current_task': current_task.task_name if current_task else "Unknown",
                        'task_progress': f"{composite_job.current_task_index + 1}/{len(composite_job.tasks)}"
                    },
                    'progress_info': progress_info
                })
        
        # Render using template
        html_content = templates.get_template("partials/jobs/current_jobs_list.html").render(
            current_jobs=current_jobs,
            message="No operations currently running.",
            padding="4"
        )
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        error_html = templates.get_template("partials/jobs/error_state.html").render(
            message=f"Error loading current operations: {str(e)}",
            padding="4"
        )
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
async def get_job_output(job_id: str, last_n_lines: int = 100, db: Session = Depends(get_db)):
    """Get job output lines"""
    # Check if this is a composite job first
    db_job = db.query(Job).filter(Job.job_uuid == job_id).first()
    if db_job and db_job.job_type == "composite":
        # Get composite job output
        from app.services.composite_job_manager import composite_job_manager
        composite_job = composite_job_manager.jobs.get(job_id)
        if not composite_job:
            raise HTTPException(status_code=404, detail="Composite job not found")
        
        # Get current task output if job is running
        current_task_output = []
        if composite_job.status == "running" and composite_job.current_task_index < len(composite_job.tasks):
            current_task = composite_job.tasks[composite_job.current_task_index]
            lines = list(current_task.output_lines)
            if last_n_lines:
                lines = lines[-last_n_lines:]
            current_task_output = lines
        
        return {
            'job_id': job_id,
            'job_type': 'composite',
            'status': composite_job.status,
            'current_task_index': composite_job.current_task_index,
            'total_tasks': len(composite_job.tasks),
            'current_task_output': current_task_output,
            'started_at': composite_job.started_at.isoformat(),
            'completed_at': composite_job.completed_at.isoformat() if composite_job.completed_at else None
        }
    else:
        # Get regular borg job output
        output = await borg_job_manager.get_job_output_stream(job_id, last_n_lines=last_n_lines)
        
        if 'error' in output:
            raise HTTPException(status_code=404, detail=output['error'])
        
        return output

@router.get("/{job_id}/stream")
async def stream_job_output(job_id: str, db: Session = Depends(get_db)):
    """Stream real-time job output via Server-Sent Events"""
    async def event_generator():
        try:
            # Check if this is a composite job first
            db_job = db.query(Job).filter(Job.job_uuid == job_id).first()
            if db_job and db_job.job_type == "composite":
                # Stream composite job output
                from app.services.composite_job_manager import composite_job_manager
                event_queue = composite_job_manager.subscribe_to_events()
                
                try:
                    # Send initial state
                    composite_job = composite_job_manager.jobs.get(job_id)
                    if composite_job:
                        yield f"data: {json.dumps({'type': 'initial_state', 'job_id': job_id, 'status': composite_job.status})}\n\n"
                    
                    # Stream events
                    while True:
                        try:
                            event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                            # Only send events for this job
                            if event.get('job_id') == job_id:
                                yield f"data: {json.dumps(event)}\n\n"
                        except asyncio.TimeoutError:
                            yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                            break
                finally:
                    composite_job_manager.unsubscribe_from_events(event_queue)
            else:
                # Stream regular borg job output
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