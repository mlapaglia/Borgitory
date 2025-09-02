import asyncio
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.models.database import Repository, Job, get_db
from app.models.schemas import Job as JobSchema, BackupRequest
from app.services.borg_service import borg_service
from app.services.docker_service import docker_service

router = APIRouter()


async def create_backup_task(repository_id: int, backup_request: BackupRequest, job_id: int):
    """Background task to handle backup creation"""
    from app.models.database import SessionLocal
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting backup task for repository_id={repository_id}, job_id={job_id}")
    
    db = SessionLocal()
    try:
        # Get fresh instances from the new session
        job = db.query(Job).filter(Job.id == job_id).first()
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        
        if not job:
            logger.error(f"Job {job_id} not found in database")
            return
        if not repository:
            logger.error(f"Repository {repository_id} not found in database")
            job.status = "failed"
            job.error = f"Repository {repository_id} not found"
            job.finished_at = datetime.utcnow()
            db.commit()
            return
        
        logger.info(f"Found job {job.id} and repository {repository.name}")
        
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        logger.info(f"Job {job.id} status updated to running")
        
        logger.info(f"Starting Borg backup with source_path={backup_request.source_path}, compression={backup_request.compression}, dry_run={backup_request.dry_run}")
        
        log_output = []
        try:
            async for progress in borg_service.create_backup(
                repository=repository,
                source_path=backup_request.source_path,
                compression=backup_request.compression,
                dry_run=backup_request.dry_run
            ):
                logger.info(f"Backup progress: {progress}")
                if progress.get("type") == "log":
                    log_output.append(progress["message"])
                elif progress.get("type") == "error":
                    job.status = "failed"
                    job.error = progress["message"]
                    job.finished_at = datetime.utcnow()
                    job.log_output = "\n".join(log_output)
                    db.commit()
                    return
                elif progress.get("type") == "started":
                    job.container_id = progress["container_id"]
                    db.commit()
                elif progress.get("type") == "completed":
                    job.status = "completed" if progress["status"] == "success" else "failed"
                    job.finished_at = datetime.utcnow()
                    job.log_output = "\n".join(log_output)
                    db.commit()
                    return
        except Exception as backup_error:
            logger.error(f"Backup service error: {backup_error}")
            job.status = "failed"
            job.error = str(backup_error)
            job.finished_at = datetime.utcnow()
            job.log_output = "\n".join(log_output)
            db.commit()
            return
        
        job.status = "completed"
        job.finished_at = datetime.utcnow()
        job.log_output = "\n".join(log_output)
        db.commit()
        
    except Exception as e:
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error = str(e)
                job.finished_at = datetime.utcnow()
                db.commit()
        except:
            pass
    finally:
        db.close()


@router.post("/backup")
async def create_backup(
    backup_request: BackupRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    repository = db.query(Repository).filter(
        Repository.id == backup_request.repository_id
    ).first()
    
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    job = Job(
        repository_id=repository.id,
        type="backup",
        status="pending"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    background_tasks.add_task(create_backup_task, repository.id, backup_request, job.id)
    
    return {"job_id": job.id, "status": "started"}


@router.get("/", response_model=List[JobSchema])
def list_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.id.desc()).offset(skip).limit(limit).all()
    return jobs


@router.get("/{job_id}", response_model=JobSchema)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_job_progress(job_id: int, db: Session = Depends(get_db)):
    """Stream real-time job progress via Server-Sent Events"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    async def event_generator():
        while True:
            db.refresh(job)
            yield {
                "event": "job_update",
                "data": {
                    "id": job.id,
                    "status": job.status,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None
                }
            }
            
            if job.status in ["completed", "failed"]:
                break
                
            await asyncio.sleep(1)
    
    return EventSourceResponse(event_generator())


@router.delete("/{job_id}")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status == "running" and job.container_id:
        # TODO: Implement container cancellation
        pass
    
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Job cancelled successfully"}


@router.get("/test/docker")
def test_docker_connectivity():
    """Test Docker connectivity and image availability"""
    import logging
    from app.config import BORG_DOCKER_IMAGE
    
    logger = logging.getLogger(__name__)
    
    try:
        # Test basic Docker connectivity
        docker_info = docker_service.client.info()
        logger.info(f"Docker info: {docker_info}")
        
        # Test image availability
        try:
            image = docker_service.client.images.get(BORG_DOCKER_IMAGE)
            image_available = True
            image_id = image.id
        except Exception as e:
            image_available = False
            image_id = None
            logger.warning(f"Borg image not available: {e}")
        
        # Test container list
        containers = docker_service.client.containers.list()
        
        return {
            "docker_connected": True,
            "docker_version": docker_info.get("ServerVersion", "unknown"),
            "borg_image": BORG_DOCKER_IMAGE,
            "image_available": image_available,
            "image_id": image_id,
            "running_containers": len(containers)
        }
        
    except Exception as e:
        logger.error(f"Docker test failed: {e}")
        return {
            "docker_connected": False,
            "error": str(e),
            "borg_image": BORG_DOCKER_IMAGE
        }